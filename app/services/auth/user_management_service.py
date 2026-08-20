"""Admin-facing user CRUD within one portal entity (a warehouse admin managing warehouse users,
a store admin managing store users, etc.) — shared implementation, mounted per-portal."""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    CannotModifySelfStatusException,
    EmailAlreadyExistsException,
    RoleNotCreatableException,
    UserNotFoundException,
)
from app.core.security import generate_opaque_token, hash_opaque_token, hash_password
from app.constants.roles import CREATABLE_ROLES_BY_PORTAL
from app.models.user import PasswordResetToken, User
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository
from app.utils.pagination import PaginationParams


class UserManagementService:
    def __init__(self, session: Session):
        self.session = session
        self.users = UserRepository(session)
        self.tokens = AuthTokenRepository(session)

    def list_users(
        self,
        portal_type,
        entity_id: uuid.UUID,
        params: PaginationParams,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        return self.users.list_in_entity(portal_type, entity_id, params, search, role, status, date_from, date_to)

    def get_user(self, portal_type, entity_id: uuid.UUID, user_id: uuid.UUID) -> User:
        user = self.users.get_in_entity(portal_type, entity_id, user_id)
        if not user:
            raise UserNotFoundException()
        return user

    def create_user(
        self,
        portal_type,
        entity_id: uuid.UUID,
        first_name: str,
        last_name: str,
        email: str,
        role: str,
        phone: str,
        temporary_password: str,
    ) -> User:
        portal_key = portal_type.value if hasattr(portal_type, "value") else portal_type
        if role not in CREATABLE_ROLES_BY_PORTAL.get(portal_key, []):
            raise RoleNotCreatableException(role)
        if self.users.get_by_portal_email(portal_type, email):
            raise EmailAlreadyExistsException()
        user = User(
            code=self.users.next_code(portal_type),
            portal_type=portal_type,
            entity_id=entity_id,
            email=email,
            password_hash=hash_password(temporary_password),
            name=f"{first_name} {last_name}".strip(),
            role=role,
            phone=phone,
            status="active",
        )
        self.users.add(user)
        self.session.commit()
        return user

    def update_user(self, portal_type, entity_id: uuid.UUID, user_id: uuid.UUID, **fields) -> User:
        user = self.get_user(portal_type, entity_id, user_id)
        new_email = fields.get("email")
        if new_email and new_email != user.email and self.users.get_by_portal_email(portal_type, new_email):
            raise EmailAlreadyExistsException()
        for key, value in fields.items():
            if value is not None:
                setattr(user, key, value)
        self.session.commit()
        return user

    def update_status(self, portal_type, entity_id: uuid.UUID, user_id: uuid.UUID, status: str, caller: User) -> User:
        if user_id == caller.id and status == "inactive":
            raise CannotModifySelfStatusException()
        user = self.get_user(portal_type, entity_id, user_id)
        user.status = status
        self.session.commit()
        return user

    def trigger_password_reset(self, portal_type, entity_id: uuid.UUID, user_id: uuid.UUID) -> None:
        user = self.get_user(portal_type, entity_id, user_id)
        token = generate_opaque_token()
        self.tokens.add_reset_token(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_opaque_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_RESET_TOKEN_TTL_HOURS),
            )
        )
        self.session.commit()
        # TODO(notifications): email `token` to the user — see the same note in
        # AuthService.request_password_reset.
