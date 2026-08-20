"""Warehouse entity, its roster links to vendors/stores, and its zones/stock-movement ledger.
Reconciled from both Backend-WH-Retail (tax_jurisdiction/manager_id, full CRUD) and
super-admin-backend (native enums, zones, stock movements, approval workflow) — see the
consolidation plan for the per-column rationale.
"""
import enum
import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class WarehouseStatus(str, enum.Enum):
    PENDING_APPROVAL = "Pending Approval"
    ACTIVE = "Active"
    REJECTED = "Rejected"
    SUSPENDED = "Suspended"
    BLOCKED = "Blocked"


class WarehouseVendorLinkStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class WarehouseStoreLinkStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MovementType(str, enum.Enum):
    INBOUND = "Inbound"
    OUTBOUND = "Outbound"
    TRANSFER = "Transfer"
    ADJUSTMENT = "Adjustment"
    RETURN = "Return"


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    tax_jurisdiction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    license_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capacity_sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    established_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    working_days: Mapped[str | None] = mapped_column(String(50), nullable=True)
    low_stock_warning_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    critical_stock_warning_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operating_hours_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    operating_hours_to: Mapped[time | None] = mapped_column(Time, nullable=True)
    status: Mapped[WarehouseStatus] = mapped_column(
        Enum(WarehouseStatus, name="warehouse_status", values_callable=_values),
        nullable=False, default=WarehouseStatus.PENDING_APPROVAL, server_default=WarehouseStatus.PENDING_APPROVAL.value,
    )
    registered_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    zones: Mapped[list["WarehouseZone"]] = relationship(back_populates="warehouse", cascade="all, delete-orphan")


class WarehouseVendorLink(Base):
    __tablename__ = "warehouse_vendor_links"
    __table_args__ = (UniqueConstraint("warehouse_id", "vendor_id", name="uq_warehouse_vendor_links"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[WarehouseVendorLinkStatus] = mapped_column(
        Enum(WarehouseVendorLinkStatus, name="warehouse_vendor_link_status", values_callable=_values),
        nullable=False, default=WarehouseVendorLinkStatus.ACTIVE, server_default=WarehouseVendorLinkStatus.ACTIVE.value,
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WarehouseStoreLink(Base):
    __tablename__ = "warehouse_store_links"
    __table_args__ = (UniqueConstraint("warehouse_id", "store_id", name="uq_warehouse_store_links"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[WarehouseStoreLinkStatus] = mapped_column(
        Enum(WarehouseStoreLinkStatus, name="warehouse_store_link_status", values_callable=_values),
        nullable=False, default=WarehouseStoreLinkStatus.ACTIVE, server_default=WarehouseStoreLinkStatus.ACTIVE.value,
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WarehouseZone(Base):
    """Super-admin-only concept (Backend-WH-Retail had no zone/utilization tracking at all) —
    kept as a real feature per the consolidation plan."""

    __tablename__ = "warehouse_zones"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    utilized_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    warehouse: Mapped["Warehouse"] = relationship(back_populates="zones")

    @property
    def utilized_pct(self) -> int:
        return round(100 * self.utilized_units / self.capacity) if self.capacity else 0

    @property
    def status(self) -> str:
        pct = self.utilized_pct
        if pct >= 100:
            return "Full"
        if pct >= 80:
            return "Near Capacity"
        return "Active"


class WarehouseStockMovement(Base):
    """Super-admin-only ledger view — kept as a real feature per the consolidation plan."""

    __tablename__ = "warehouse_stock_movements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[MovementType] = mapped_column(
        Enum(MovementType, name="warehouse_movement_type", values_callable=_values), nullable=False
    )
    sku_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="Pcs", server_default="Pcs")
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    from_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
