"""Core login/session/profile business logic — shared by all four portals via
require_portal(portal_type). No SQL here; all persistence goes through the repository layer."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import InvalidCredentialsException, InvalidTokenException, PortalAccessNotApprovedException, UserNotFoundException
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from app.models.user import PasswordResetToken, RefreshToken, User, UserAccountSettings, UserNotificationPrefs, UserStatus
from app.models.retail import Store, StoreStatus
from app.models.vendor import Vendor, VendorStatus
from app.models.warehouse import Warehouse, WarehouseStatus
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.users = UserRepository(session)
        self.tokens = AuthTokenRepository(session)

    def authenticate(self, portal_type, email: str, password: str) -> User:
        user = self.users.get_by_portal_email(portal_type, email)
        if not user or not verify_password(password, user.password_hash) or user.status != UserStatus.ACTIVE:
            raise InvalidCredentialsException("Incorrect email or password")
        # A vendor's login account can be active while the vendor itself is still awaiting
        # (or has lost) Super Admin approval — block portal entry in that case rather than
        # only checking the login account's own status.
        if portal_type == "vendor" and user.entity_id:
            vendor = self.session.get(Vendor, user.entity_id)
            if vendor and vendor.status != VendorStatus.ACTIVE:
                raise PortalAccessNotApprovedException(vendor.status.value)
        # Same story for a newly self-registered warehouse: register_warehouse() creates its
        # wh-admin login as ACTIVE immediately, before Super Admin has approved the warehouse
        # itself — block portal entry until Warehouse.status is ACTIVE.
        if portal_type == "warehouse" and user.entity_id:
            warehouse = self.session.get(Warehouse, user.entity_id)
            if warehouse and warehouse.status != WarehouseStatus.ACTIVE:
                raise PortalAccessNotApprovedException(warehouse.status.value, entity_label="Warehouse")
        # And the same again for a self-registered store: register_store() creates its
        # store-admin login as ACTIVE immediately, before Super Admin has approved the store.
        if portal_type == "store" and user.entity_id:
            store = self.session.get(Store, user.entity_id)
            if store and store.status != StoreStatus.ACTIVE:
                raise PortalAccessNotApprovedException(store.status.value, entity_label="Store")
        user.last_login_at = datetime.now(timezone.utc)
        self.session.commit()
        return user

    def issue_tokens(self, user: User) -> tuple[str, str]:
        access_token = create_access_token(user.id, user.portal_type.value, user.role)
        refresh_token = generate_opaque_token()
        self.tokens.add_refresh_token(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_opaque_token(refresh_token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        self.session.commit()
        return access_token, refresh_token

    def login(self, portal_type, email: str, password: str) -> tuple[str, str, User]:
        user = self.authenticate(portal_type, email, password)
        access_token, refresh_token = self.issue_tokens(user)
        return access_token, refresh_token, self.attach_entity_name(user)

    def refresh_access_token(self, refresh_token: str) -> str:
        row = self.tokens.get_refresh_token_by_hash(hash_opaque_token(refresh_token))
        if not row or row.revoked_at is not None or row.expires_at < datetime.now(timezone.utc):
            raise InvalidTokenException("Refresh token is invalid, expired, or revoked")
        user = self.users.get_by_id(row.user_id)
        if not user or user.status != UserStatus.ACTIVE:
            raise InvalidTokenException("Invalid or expired refresh token")
        return create_access_token(user.id, user.portal_type.value, user.role)

    def revoke_refresh_token(self, refresh_token: str) -> None:
        row = self.tokens.get_refresh_token_by_hash(hash_opaque_token(refresh_token))
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            self.session.commit()

    def request_password_reset(self, portal_type, email: str) -> None:
        """Always returns None regardless of whether the account exists — never let this
        endpoint leak account existence."""
        user = self.users.get_by_portal_email(portal_type, email)
        if not user:
            return
        token = generate_opaque_token()
        self.tokens.add_reset_token(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_opaque_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_RESET_TOKEN_TTL_HOURS),
            )
        )
        self.session.commit()
        # TODO(notifications): send `token` via an email-sending integration once one is wired
        # up. Deliberately not returning it in the API response.

    def reset_password(self, token: str, new_password: str) -> None:
        row = self.tokens.get_reset_token_by_hash(hash_opaque_token(token))
        if not row or row.used_at is not None or row.expires_at < datetime.now(timezone.utc):
            raise InvalidTokenException("Reset token is invalid, expired, or already used")
        user = self.users.get_by_id(row.user_id)
        if not user:
            raise UserNotFoundException()
        user.password_hash = hash_password(new_password)
        row.used_at = datetime.now(timezone.utc)
        self.session.commit()

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsException("Incorrect current password")
        user.password_hash = hash_password(new_password)
        self.session.commit()

    def get_entity_name(self, user: User) -> str | None:
        """Warehouse/store name for the account's own entity_id — UserOut has no FK
        relationship to either table (entity_id points at one or the other depending on
        portal_type, never both), so this is a plain lookup rather than an ORM join."""
        if not user.entity_id:
            return None
        if user.portal_type.value == "warehouse":
            from app.models.warehouse import Warehouse  # deferred: Phase 3 domain

            entity = self.session.get(Warehouse, user.entity_id)
        elif user.portal_type.value == "store":
            from app.models.retail import Store  # deferred: Phase 3 domain

            entity = self.session.get(Store, user.entity_id)
        else:
            return None
        return entity.name if entity else None

    def attach_entity_name(self, user: User) -> User:
        user.entity_name = self.get_entity_name(user)
        return user

    def update_me(self, user: User, name: str | None, phone: str | None, email: str | None) -> User:
        if name is not None:
            user.name = name
        if phone is not None:
            user.phone = phone
        if email is not None:
            user.email = email
        self.session.commit()
        return self.attach_entity_name(user)

    def get_or_create_account_settings(self, user_id: uuid.UUID) -> UserAccountSettings:
        row = self.tokens.get_account_settings(user_id)
        if not row:
            row = self.tokens.add_account_settings(UserAccountSettings(user_id=user_id))
            self.session.commit()
        return row

    def update_account_settings(self, user_id: uuid.UUID, **fields) -> UserAccountSettings:
        row = self.get_or_create_account_settings(user_id)
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        self.session.commit()
        return row

    def get_or_create_notification_prefs(self, user_id: uuid.UUID) -> UserNotificationPrefs:
        row = self.tokens.get_notification_prefs(user_id)
        if not row:
            row = self.tokens.add_notification_prefs(UserNotificationPrefs(user_id=user_id))
            self.session.commit()
        return row

    def update_notification_prefs(self, user_id: uuid.UUID, **fields) -> UserNotificationPrefs:
        row = self.get_or_create_notification_prefs(user_id)
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        self.session.commit()
        return row
