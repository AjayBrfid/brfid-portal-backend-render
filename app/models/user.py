"""Shared login table across all four portals (one row per login, discriminated by
portal_type), plus its supporting auth tables. Reconciled from all three source projects: the
User shape (native enums, String(20) code, unique (portal_type, email)) follows
brfid-portal-backend's convention; RefreshToken/PasswordResetToken/UserAccountSettings/
UserNotificationPrefs are adopted from Backend-WH-Retail, the only source project with a
revocable (opaque, hashed) refresh-token flow and these preference tables at all.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class PortalType(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    WAREHOUSE = "warehouse"
    VENDOR = "vendor"
    STORE = "store"  # URL prefix is /retail/... but the stored portal_type value is "store"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class User(Base):
    """entity_id points at warehouses/vendors/stores.id depending on portal_type, and is NULL
    for super_admin (no entity table for the platform operator itself). It's a plain UUID with
    no DB-level FK since it's genuinely polymorphic — resolved in code (see
    app/services/auth/auth_service.py's get_entity_name), never via an ORM relationship."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("portal_type", "email", name="uq_users_portal_type_email"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    portal_type: Mapped[PortalType] = mapped_column(
        Enum(PortalType, name="portal_type", values_callable=_values), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", values_callable=_values),
        nullable=False, default=UserStatus.ACTIVE, server_default=UserStatus.ACTIVE.value,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RefreshToken(Base):
    """Persisted so /auth/logout and /auth/refresh can actually revoke a session server-side —
    a pure stateless JWT refresh token can never be invalidated before it expires. Only the hash
    is stored; the opaque token itself is never persisted."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserAccountSettings(Base):
    """Backs GET/PATCH /me/account-settings (language/timezone/dateFormat/darkMode panel)."""

    __tablename__ = "user_account_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(50), default="English", server_default="English")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", server_default="Asia/Kolkata")
    date_format: Mapped[str] = mapped_column(String(20), default="DD Mon YYYY", server_default="DD Mon YYYY")
    dark_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class UserNotificationPrefs(Base):
    """Backs GET/PATCH /me/notification-prefs (the 6-toggle preference panel)."""

    __tablename__ = "user_notification_prefs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    notify_new_pr: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_vendor_rfq_response: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_store_return: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_po_ready_for_inspection: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_transfer_order_status_change: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_daily_summary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
