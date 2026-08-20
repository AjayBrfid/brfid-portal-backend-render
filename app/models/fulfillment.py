"""Warehouse-side fulfilment: purchase requests raised by a store, how each gets fulfilled
(from stock, via a fresh RFQ, or a split of both), the resulting transfer orders, and the
warehouse inventory ledger + reservations backing all of it.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class PurchaseRequestPriority(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class PurchaseRequestApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class FulfilmentType(str, enum.Enum):
    STOCK = "stock"
    RFQ = "rfq"
    SPLIT = "split"


class FulfilmentRefType(str, enum.Enum):
    TRANSFER_ORDER = "transfer_order"
    RFQ = "rfq"


class TransferOrderStatus(str, enum.Enum):
    PENDING = "Pending"
    DISPATCHED = "Dispatched"
    DELIVERED = "Delivered"
    COMPLETED = "Completed"


class TransferOrderSourceType(str, enum.Enum):
    WAREHOUSE_STOCK = "Warehouse Stock"
    VENDOR_PROCUREMENT = "Vendor Procurement"
    RETURN_REPLENISHMENT = "Return Replenishment"
    COMBINED = "Combined Stock + Vendor"


class PurchaseRequest(Base):
    """Deliberately has no stored `status` column — display status is derived by joining to
    whichever TransferOrder/Rfq actually fulfilled it (both Backend-WH-Retail and
    super-admin-backend independently arrived at this design)."""

    __tablename__ = "purchase_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False)
    requested_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    required_by: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[PurchaseRequestPriority] = mapped_column(
        Enum(PurchaseRequestPriority, name="purchase_request_priority", values_callable=_values),
        nullable=False, default=PurchaseRequestPriority.MEDIUM, server_default=PurchaseRequestPriority.MEDIUM.value,
    )
    approval_status: Mapped[PurchaseRequestApprovalStatus] = mapped_column(
        Enum(PurchaseRequestApprovalStatus, name="purchase_request_approval_status", values_callable=_values),
        nullable=False, default=PurchaseRequestApprovalStatus.PENDING, server_default=PurchaseRequestApprovalStatus.PENDING.value,
    )
    fulfilment_type: Mapped[FulfilmentType | None] = mapped_column(
        Enum(FulfilmentType, name="fulfilment_type", values_callable=_values), nullable=True
    )
    fulfilment_ref_type: Mapped[FulfilmentRefType | None] = mapped_column(
        Enum(FulfilmentRefType, name="fulfilment_ref_type", values_callable=_values), nullable=True
    )
    fulfilment_ref_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class TransferOrder(Base):
    __tablename__ = "transfer_orders"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    pr_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_requests.id"), nullable=True, index=True)
    # use_alter breaks the transfer_orders <-> store_returns creation cycle: this FK is applied
    # via a deferred ALTER TABLE after both tables exist (see AuditLog note in the consolidation
    # plan re: unnamed circular FKs being silently dropped by autogenerate otherwise).
    return_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("store_returns.id", use_alter=True, name="fk_transfer_orders_return_id"),
        nullable=True, index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[TransferOrderSourceType] = mapped_column(
        Enum(TransferOrderSourceType, name="transfer_order_source_type", values_callable=_values), nullable=False
    )
    status: Mapped[TransferOrderStatus] = mapped_column(
        Enum(TransferOrderStatus, name="transfer_order_status", values_callable=_values),
        nullable=False, default=TransferOrderStatus.PENDING, server_default=TransferOrderStatus.PENDING.value, index=True,
    )
    transporter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    packages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Inventory(Base):
    __tablename__ = "inventory"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True
    )
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id", ondelete="CASCADE"), primary_key=True
    )
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    available: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    returns_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InventoryReservation(Base):
    """`pr_id` XOR `return_id` — exactly one is set, app-enforced, never both — so the same
    reservation machinery serves a warehouse-side Purchase Request shortfall and a retail-side
    Store Return replenishment shortfall (the latter is a Backend-WH-Retail-only capability,
    absent from brfid-portal-backend, preserved here per the consolidation plan)."""

    __tablename__ = "inventory_reservations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False)
    pr_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_requests.id"), nullable=True, index=True)
    return_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("store_returns.id"), nullable=True, index=True)
    reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    total_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
