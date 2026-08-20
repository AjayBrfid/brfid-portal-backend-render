"""In-app notifications, shared across all four portals via the same users table's
portal_type discriminator. `entity_id` is a polymorphic reference (the thing this notification
is about — a PO, an RFQ, a transfer order, etc.), intentionally not FK-constrained since it can
point at any one of several different tables depending on `entity_type`.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class StoreNotificationMute(Base):
    """A coarse per-role mute switch at a single store (e.g. mute all 'store-manager'-role
    alerts at this store) — distinct from the per-user, per-event-type UserNotificationPrefs
    toggles in app/models/user.py, which warehouse uses instead. Retail-only concept."""

    __tablename__ = "store_notification_mutes"

    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), primary_key=True)
    muted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
