import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment import FreightPayment, Payment
from app.utils.pagination import PaginationParams, paginate


class PaymentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, payment: Payment) -> Payment:
        self.session.add(payment)
        self.session.flush()
        return payment

    def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        return self.session.get(Payment, payment_id)

    def list_for_vendor(
        self, vendor_id: uuid.UUID, params: PaginationParams,
        date_from: date | None = None, date_to: date | None = None,
    ):
        from app.models.procurement import PurchaseOrder

        stmt = (
            select(Payment)
            .join(PurchaseOrder, PurchaseOrder.id == Payment.po_id)
            .where(PurchaseOrder.vendor_id == vendor_id)
        )
        if date_from:
            stmt = stmt.where(Payment.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
        if date_to:
            stmt = stmt.where(Payment.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
        stmt = stmt.order_by(Payment.created_at.desc())
        return paginate(self.session, stmt, params)

    def summary_for_vendor(self, vendor_id: uuid.UUID) -> dict:
        from sqlalchemy import func

        from app.models.procurement import PurchaseOrder

        rows = self.session.execute(
            select(Payment.status, func.count(), func.coalesce(func.sum(Payment.amount), 0))
            .join(PurchaseOrder, PurchaseOrder.id == Payment.po_id)
            .where(PurchaseOrder.vendor_id == vendor_id)
            .group_by(Payment.status)
        ).all()
        return {status.value: {"count": count, "amount": float(amount)} for status, count, amount in rows}


class FreightPaymentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, row: FreightPayment) -> FreightPayment:
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, freight_payment_id: uuid.UUID) -> FreightPayment | None:
        return self.session.get(FreightPayment, freight_payment_id)

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        """`linked_id` is polymorphic (a shipments.id or a vendor_returns.id depending on
        linked_type), so there's no single join back to vendor_id — resolve both link types'
        vendor-owned ids separately, then filter in Python before paginating. Freight payment
        volumes are low enough per vendor that this two-query approach is simpler and safer
        than trying to force it into one SQL statement."""
        from app.models.procurement import PurchaseOrder
        from app.models.shipping import Asn, Shipment
        from app.models.vendor_return import VendorReturn

        shipment_ids = set(
            self.session.execute(
                select(Shipment.id)
                .join(Asn, Asn.id == Shipment.asn_id)
                .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
                .where(PurchaseOrder.vendor_id == vendor_id)
            ).scalars().all()
        )
        return_ids = set(
            self.session.execute(select(VendorReturn.id).where(VendorReturn.vendor_id == vendor_id)).scalars().all()
        )

        stmt = select(FreightPayment).where(
            ((FreightPayment.linked_type == "shipment") & FreightPayment.linked_id.in_(shipment_ids or [None]))
            | ((FreightPayment.linked_type == "vendor_return") & FreightPayment.linked_id.in_(return_ids or [None]))
        )
        if status:
            stmt = stmt.where(FreightPayment.status == status)
        stmt = stmt.order_by(FreightPayment.id.desc())
        return paginate(self.session, stmt, params)

    def get_for_vendor(self, vendor_id: uuid.UUID, freight_payment_id: uuid.UUID) -> FreightPayment | None:
        row = self.get_by_id(freight_payment_id)
        if not row:
            return None
        if row.linked_type.value == "shipment":
            from app.models.procurement import PurchaseOrder
            from app.models.shipping import Asn, Shipment

            owner_vendor_id = self.session.execute(
                select(PurchaseOrder.vendor_id)
                .join(Asn, Asn.po_id == PurchaseOrder.id)
                .join(Shipment, Shipment.asn_id == Asn.id)
                .where(Shipment.id == row.linked_id)
            ).scalar_one_or_none()
        else:
            from app.models.vendor_return import VendorReturn

            owner_vendor_id = self.session.execute(select(VendorReturn.vendor_id).where(VendorReturn.id == row.linked_id)).scalar_one_or_none()
        return row if owner_vendor_id == vendor_id else None
