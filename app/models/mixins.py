"""Shared mixins for models that don't need bespoke enum/constraint handling. Tables with a
native Postgres enum status column or composite PK generally declare `id`/timestamps explicitly
instead (see app/models/user.py) since the enum-per-column convention (adopted per the
consolidation plan) reads more clearly spelled out than hidden behind a mixin.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
