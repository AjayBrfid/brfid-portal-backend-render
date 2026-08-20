"""Retail/Store domain: the Store entity itself plus retail-only tables that the original
cross-portal schema doc never modeled (per-store inventory/visibility/pricing, the admin-edit-
requires-approval workflow, and store returns) — all flagged as deliberate additions in
Backend-WH-Retail's own docstrings and kept here per the consolidation plan.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class StoreStatus(str, enum.Enum):
    PENDING_APPROVAL = "Pending Approval"
    ACTIVE = "Active"
    REJECTED = "Rejected"
    INACTIVE = "Inactive"
    BLOCKED = "Blocked"


class StoreType(str, enum.Enum):
    FLAGSHIP = "Flagship"
    STANDARD = "Standard"
    OUTLET = "Outlet"


class StoreApprovalStatus(str, enum.Enum):
    WAITING = "waiting"
    APPROVED = "approved"


class StoreReturnDecision(str, enum.Enum):
    REPLENISH = "replenish"
    WRITEOFF = "writeoff"


class StoreReturnStatus(str, enum.Enum):
    PENDING = "pending"
    REPLENISHED = "replenished"
    DISPATCHED = "dispatched"
    WRITTENOFF = "writtenoff"


class ReceivingItemStatus(str, enum.Enum):
    PENDING = "Pending"
    VERIFIED = "Verified"
    RETURN_REQUESTED = "Return Requested"
    WRITTEN_OFF = "Written Off"


class ReceivingItemCondition(str, enum.Enum):
    GOOD = "Good"
    MISSING_DEFECTIVE = "Missing/Defective"


class ReceivingReturnType(str, enum.Enum):
    REPLENISHMENT = "Replenishment"
    WRITE_OFF = "Write-off"


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    store_type: Mapped[StoreType] = mapped_column(Enum(StoreType, name="store_type", values_callable=_values), nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    years_in_operation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    documents: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=20, server_default="20")
    status: Mapped[StoreStatus] = mapped_column(
        Enum(StoreStatus, name="store_status", values_callable=_values),
        nullable=False, default=StoreStatus.PENDING_APPROVAL, server_default=StoreStatus.PENDING_APPROVAL.value,
    )
    opened_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StoreApproval(Base):
    """Backs retail's admin-edit-requires-approval workflow — an Admin's settings change is
    queued here and applied only once a Manager approves it (or vice versa, per the actor's
    role); a Manager's own change applies immediately with no row created here at all."""

    __tablename__ = "store_approvals"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[StoreApprovalStatus] = mapped_column(
        Enum(StoreApprovalStatus, name="store_approval_status", values_callable=_values),
        nullable=False, default=StoreApprovalStatus.WAITING, server_default=StoreApprovalStatus.WAITING.value,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoreInventory(Base):
    """Per-store stock ledger — the reconciled cross-portal schema only ever modeled
    *warehouse*-level inventory (see app/models/fulfillment.py's Inventory); retail needed its
    own per-store stock model from scratch. Column names (`quantity`/`reorder_level`) follow
    super-admin-backend's convention, consistent with skus.reorder_level."""

    __tablename__ = "store_inventory"

    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reorder_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StoreProductSettings(Base):
    """Per-store product visibility/removal — Backend-WH-Retail-only feature, kept as a real
    feature (super-admin-backend's schema has no equivalent)."""

    __tablename__ = "store_product_settings"

    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id", ondelete="CASCADE"), primary_key=True
    )
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class StoreDiscount(Base):
    """Per-store, per-SKU-variant discount — Backend-WH-Retail-only feature, kept as a real
    feature."""

    __tablename__ = "store_discounts"

    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id", ondelete="CASCADE"), primary_key=True
    )
    pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StoreReturn(Base):
    """A store's return of goods back to its supplying warehouse — resolved either by warehouse
    replenishment (a new TransferOrder) or a write-off, or (per Backend-WH-Retail's
    return-triggered-RFQ capability, preserved here) a fresh RFQ when the warehouse itself has
    no stock to replenish from. `pr_id` is nullable (adopted from brfid-portal-backend's stance
    — a return isn't always tied to a specific fulfilled purchase request).
    """

    __tablename__ = "store_returns"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    pr_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_requests.id"), nullable=True)
    store_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decision: Mapped[StoreReturnDecision] = mapped_column(
        Enum(StoreReturnDecision, name="store_return_decision", values_callable=_values), nullable=False
    )
    status: Mapped[StoreReturnStatus] = mapped_column(
        Enum(StoreReturnStatus, name="store_return_status", values_callable=_values),
        nullable=False, default=StoreReturnStatus.PENDING, server_default=StoreReturnStatus.PENDING.value,
    )
    # Plain FK (not use_alter) — the transfer_orders <-> store_returns creation-order cycle is
    # broken on the other side, by TransferOrder.return_id (see app/models/fulfillment.py).
    resolution_transfer_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("transfer_orders.id"), nullable=True
    )
    # use_alter breaks the store_returns <-> rfqs creation cycle (same pattern as
    # resolution_transfer_order_id's sibling FK above, and required at the model level too —
    # not just in the Alembic migration — so Base.metadata.create_all()/drop_all() (used
    # directly by the test suite, bypassing Alembic) can also resolve the cycle.
    resolution_rfq_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rfqs.id", use_alter=True, name="fk_store_returns_resolution_rfq_id"),
        nullable=True,
    )


class ReceivingItem(Base):
    """One row per SKU line on an incoming transfer-order shipment, awaiting the store's
    physical goods verification. Raising an issue with return_type Replenishment/Write-off
    creates a StoreReturn row, reconciling retail's "Receiving" concept with warehouse's
    "Store Return" concept."""

    __tablename__ = "receiving_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transfer_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("transfer_orders.id"), nullable=False, index=True
    )
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False, index=True
    )
    expected_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ReceivingItemStatus] = mapped_column(
        Enum(ReceivingItemStatus, name="receiving_item_status", values_callable=_values),
        nullable=False, default=ReceivingItemStatus.PENDING, server_default=ReceivingItemStatus.PENDING.value,
    )
    condition: Mapped[ReceivingItemCondition | None] = mapped_column(
        Enum(ReceivingItemCondition, name="receiving_item_condition", values_callable=_values), nullable=True
    )
    issue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_type: Mapped[ReceivingReturnType | None] = mapped_column(
        Enum(ReceivingReturnType, name="receiving_return_type", values_callable=_values), nullable=True
    )
    store_return_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("store_returns.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
