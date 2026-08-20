"""Master SKU catalog — owned by Super Admin (a vendor's catalog submission becomes a real SKU
only once Super Admin reviews it and calls generate_sku, see Phase 4's vendor-catalog service).
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class SkuStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class WarehouseSkuStatusValue(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    style_code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fabric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gsm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hsn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="Pcs", server_default="Pcs")
    reorder_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[SkuStatus] = mapped_column(
        Enum(SkuStatus, name="sku_status", values_callable=_values),
        nullable=False, default=SkuStatus.ACTIVE, server_default=SkuStatus.ACTIVE.value, index=True,
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    variants: Mapped[list["SkuVariant"]] = relationship(back_populates="sku", cascade="all, delete-orphan")


class SkuVariant(Base):
    __tablename__ = "sku_variants"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False)
    variant_code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    colour: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size: Mapped[str | None] = mapped_column(String(10), nullable=True)

    sku: Mapped["Sku"] = relationship(back_populates="variants")


class WarehouseSkuStatus(Base):
    __tablename__ = "warehouse_sku_status"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True
    )
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[WarehouseSkuStatusValue] = mapped_column(
        Enum(WarehouseSkuStatusValue, name="warehouse_sku_status_value", values_callable=_values),
        nullable=False, default=WarehouseSkuStatusValue.ACTIVE, server_default=WarehouseSkuStatusValue.ACTIVE.value,
    )


class SkuSupplyingVendor(Base):
    __tablename__ = "sku_supplying_vendors"
    __table_args__ = (UniqueConstraint("sku_variant_id", "vendor_id", name="uq_sku_supplying_vendors"),)

    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id", ondelete="CASCADE"), primary_key=True
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), primary_key=True
    )
