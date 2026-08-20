import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class PaymentStatus(str, enum.Enum):
    PAID = "Paid"
    PENDING = "Pending"
    OVERDUE = "Overdue"
    PROCESSING = "Processing"


class PaymentMode(str, enum.Enum):
    NEFT = "NEFT"
    RTGS = "RTGS"
    CHEQUE = "Cheque"
    IMPS = "IMPS"


class FreightDirection(str, enum.Enum):
    VENDOR_TO_WAREHOUSE = "VENDOR_TO_WAREHOUSE"
    WAREHOUSE_TO_VENDOR = "WAREHOUSE_TO_VENDOR"


class FreightLinkedType(str, enum.Enum):
    SHIPMENT = "shipment"
    VENDOR_RETURN = "vendor_return"


class FreightPayerParty(str, enum.Enum):
    VENDOR = "vendor"
    WAREHOUSE = "warehouse"


class FreightPaymentStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    PAID = "Paid"
    OVERDUE = "Overdue"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    po_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=_values),
        nullable=False, default=PaymentStatus.PENDING, server_default=PaymentStatus.PENDING.value,
    )
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_mode: Mapped[PaymentMode | None] = mapped_column(Enum(PaymentMode, name="payment_mode", values_callable=_values), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FreightPayment(Base):
    __tablename__ = "freight_payments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    direction: Mapped[FreightDirection] = mapped_column(Enum(FreightDirection, name="freight_direction", values_callable=_values), nullable=False)
    linked_type: Mapped[FreightLinkedType] = mapped_column(Enum(FreightLinkedType, name="freight_linked_type", values_callable=_values), nullable=False)
    linked_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    transporter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payer: Mapped[FreightPayerParty] = mapped_column(
        Enum(FreightPayerParty, name="freight_payer_party", values_callable=_values),
        nullable=False, default=FreightPayerParty.VENDOR, server_default=FreightPayerParty.VENDOR.value,
    )
    base_freight: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gst_on_freight: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tds_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    net_payable_to_transporter: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    final_liability_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gta_forward_charge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[FreightPaymentStatus] = mapped_column(
        Enum(FreightPaymentStatus, name="freight_payment_status", values_callable=_values),
        nullable=False, default=FreightPaymentStatus.PENDING, server_default=FreightPaymentStatus.PENDING.value,
    )
    paid_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
