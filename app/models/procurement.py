"""RFQ -> Quotation -> Purchase Order chain. Real FKs to warehouses/purchase_requests/
sku_variants (unlike brfid-portal-backend's unconstrained UUIDs, which existed only because
its codebase never had the warehouse side at all) — that gap is exactly what this merge closes.
Rfq.return_id (RFQ raised directly from a store return's shortfall) is a Backend-WH-Retail-only
capability, preserved here.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class RfqStatus(str, enum.Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    AWAITING_QUOTATIONS = "Awaiting Quotations"
    PARTIALLY_RESPONDED = "Partially Responded"
    READY_FOR_COMPARISON = "Ready for Comparison"
    VENDOR_SELECTED = "Vendor Selected"
    PURCHASE_ORDER_GENERATED = "Purchase Order Generated"
    CLOSED = "Closed"


class QuotationStatus(str, enum.Enum):
    SUBMITTED = "Submitted"
    UNDER_EVALUATION = "Under Evaluation"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class FreightPayer(str, enum.Enum):
    VENDOR = "vendor"
    WAREHOUSE = "warehouse"


class PurchaseOrderStatus(str, enum.Enum):
    PENDING_ACCEPTANCE = "Pending Acceptance"
    ACCEPTED = "Accepted"
    IN_PRODUCTION = "In Production"
    READY_TO_SHIP = "Ready to Ship"
    DELIVERED = "Delivered"
    REJECTED = "Rejected"


class Rfq(Base):
    __tablename__ = "rfqs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    pr_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_requests.id"), nullable=True, index=True)
    return_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("store_returns.id"), nullable=True, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    required_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[RfqStatus] = mapped_column(
        Enum(RfqStatus, name="rfq_status", values_callable=_values),
        nullable=False, default=RfqStatus.DRAFT, server_default=RfqStatus.DRAFT.value, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invited_vendors: Mapped[list["RfqInvitedVendor"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")


class RfqInvitedVendor(Base):
    __tablename__ = "rfq_invited_vendors"

    rfq_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), primary_key=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), primary_key=True)

    rfq: Mapped["Rfq"] = relationship(back_populates="invited_vendors")


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rfq_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_days: Mapped[int] = mapped_column(Integer, nullable=False)
    warranty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False)
    freight_payer: Mapped[FreightPayer] = mapped_column(Enum(FreightPayer, name="freight_payer", values_callable=_values), nullable=False)
    freight_details_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotation_status", values_callable=_values),
        nullable=False, default=QuotationStatus.SUBMITTED, server_default=QuotationStatus.SUBMITTED.value,
    )
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    rfq: Mapped["Rfq"] = relationship(back_populates="quotations")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("rfqs.id"), nullable=False)
    quotation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus, name="purchase_order_status", values_callable=_values),
        nullable=False, default=PurchaseOrderStatus.PENDING_ACCEPTANCE, server_default=PurchaseOrderStatus.PENDING_ACCEPTANCE.value, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
