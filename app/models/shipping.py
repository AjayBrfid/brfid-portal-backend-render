"""ASN (Advance Shipment Notice) -> goods receipt/inspection -> shipment -> invoice chain.
Adopts brfid-portal-backend's more evolved split (goods_receipts + asn_items pulled out of a
flat Asn row) per the consolidation plan, while keeping Backend-WH-Retail's `Asn.transport_charge`
field (a real field the other side never modeled).
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class AsnDraftStatus(str, enum.Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"


class AttachmentUploaderRole(str, enum.Enum):
    VENDOR = "vendor"
    WAREHOUSE = "warehouse"


class AsnInspectionStatus(str, enum.Enum):
    AWAITING_INSPECTION = "awaiting_inspection"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    REJECTED = "rejected"


class ShipmentStatus(str, enum.Enum):
    PACKED = "Packed"
    DISPATCHED = "Dispatched"
    IN_TRANSIT = "In Transit"
    DELIVERED = "Delivered"
    DELAYED = "Delayed"


class InvoiceStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Asn(Base):
    __tablename__ = "asns"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    po_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    shipped_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    draft_status: Mapped[AsnDraftStatus] = mapped_column(
        Enum(AsnDraftStatus, name="asn_draft_status", values_callable=_values),
        nullable=False, default=AsnDraftStatus.DRAFT, server_default=AsnDraftStatus.DRAFT.value,
    )
    transport_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items: Mapped[list["AsnItem"]] = relationship(back_populates="asn", cascade="all, delete-orphan")
    attachments: Mapped[list["AsnAttachment"]] = relationship(back_populates="asn", cascade="all, delete-orphan")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="asn")


class AsnItem(Base):
    """One row per shipped SKU line on an ASN — pulled out of the flat Asn row so multi-line
    ASNs are representable (Backend-WH-Retail's flat `shipped_qty` assumed one line per ASN)."""

    __tablename__ = "asn_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asn_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("asns.id", ondelete="CASCADE"), nullable=False)
    po_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    sku_variant_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=True)
    ordered_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    shipped_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asn: Mapped["Asn"] = relationship(back_populates="items")


class AsnAttachment(Base):
    __tablename__ = "asn_attachments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asn_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("asns.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_role: Mapped[AttachmentUploaderRole] = mapped_column(
        Enum(AttachmentUploaderRole, name="asn_attachment_uploader_role", values_callable=_values), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asn: Mapped["Asn"] = relationship(back_populates="attachments")


class GoodsReceipt(Base):
    """The warehouse's inspection outcome for an ASN, split out of the flat Asn row (see
    module docstring) — one row per ASN, unique on asn_id."""

    __tablename__ = "goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asn_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("asns.id", ondelete="CASCADE"), unique=True, nullable=False)
    po_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rejected_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspection_status: Mapped[AsnInspectionStatus] = mapped_column(
        Enum(AsnInspectionStatus, name="asn_inspection_status", values_callable=_values),
        nullable=False, default=AsnInspectionStatus.AWAITING_INSPECTION, server_default=AsnInspectionStatus.AWAITING_INSPECTION.value,
    )
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    asn_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("asns.id"), nullable=False)
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    transporter: Mapped[str] = mapped_column(String(100), nullable=False)
    driver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    driver_contact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    packages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus, name="shipment_status", values_callable=_values),
        nullable=False, default=ShipmentStatus.PACKED, server_default=ShipmentStatus.PACKED.value,
    )

    asn: Mapped["Asn"] = relationship(back_populates="shipments")
    timeline_events: Mapped[list["ShipmentTimelineEvent"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")


class ShipmentTimelineEvent(Base):
    __tablename__ = "shipment_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="timeline_events")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("vendor_id", "invoice_number", name="uq_invoice_vendor_number"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    asn_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("asns.id"), nullable=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status", values_callable=_values),
        nullable=False, default=InvoiceStatus.PENDING, server_default=InvoiceStatus.PENDING.value,
    )
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
