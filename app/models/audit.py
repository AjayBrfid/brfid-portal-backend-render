"""Cross-portal audit trail. `entity_id` is a UUID (adopted from brfid-portal-backend's
convention per the consolidation plan) — every entity in this schema has a UUID primary key, so
callers must pass the entity's real id, not a display ref_code.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class AuditPortalType(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    WAREHOUSE = "warehouse"
    VENDOR = "vendor"
    STORE = "store"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    portal_type: Mapped[AuditPortalType] = mapped_column(
        Enum(AuditPortalType, name="audit_portal_type", values_callable=_values), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
