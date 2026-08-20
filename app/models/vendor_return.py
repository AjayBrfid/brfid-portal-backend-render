"""A warehouse's return of rejected/defective goods back to the vendor (created from ASN
inspection rejections — see app/services/vendor/asn_service.py). Keeps Backend-WH-Retail's
stricter FK/NOT-NULL constraints on warehouse_id/sku_variant_id/reason (real FKs, since both
sides of this relationship now live in the same codebase) plus brfid-portal-backend's native
status enum and created_at column.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class VendorReturnStatus(str, enum.Enum):
    INITIATED = "Initiated"
    APPROVED = "Approved"
    IN_TRANSIT = "In Transit"
    RECEIVED = "Received"
    REFUNDED = "Refunded"
    REJECTED = "Rejected"


class VendorReturn(Base):
    __tablename__ = "vendor_returns"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    po_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False, index=True)
    asn_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("asns.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    sku_variant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=False, index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[VendorReturnStatus] = mapped_column(
        Enum(VendorReturnStatus, name="vendor_return_status", values_callable=_values),
        nullable=False, default=VendorReturnStatus.INITIATED, server_default=VendorReturnStatus.INITIATED.value, index=True,
    )
    review_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transporter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    driver_contact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    attachments: Mapped[list["VendorReturnAttachment"]] = relationship(back_populates="vendor_return", cascade="all, delete-orphan")


class VendorReturnAttachment(Base):
    """Rejection-evidence photos/videos the warehouse attaches when it inspects and rejects
    ASN units — surfaced back to the vendor on their Returns page so they can see why."""

    __tablename__ = "vendor_return_attachments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_return_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendor_returns.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    vendor_return: Mapped["VendorReturn"] = relationship(back_populates="attachments")
