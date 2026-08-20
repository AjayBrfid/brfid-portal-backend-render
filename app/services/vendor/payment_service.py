import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.repositories.payment_repository import FreightPaymentRepository, PaymentRepository
from app.utils.pagination import PaginationParams


class PaymentService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PaymentRepository(session)

    def _to_out(self, payment) -> dict:
        return {
            "id": payment.id, "invoice_id": payment.invoice_id, "po_id": payment.po_id, "amount": float(payment.amount),
            "status": payment.status.value, "paid_date": payment.paid_date,
            "payment_mode": payment.payment_mode.value if payment.payment_mode else None, "reference_no": payment.reference_no,
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, date_from: date | None = None, date_to: date | None = None):
        rows, total = self.repo.list_for_vendor(vendor_id, params, date_from, date_to)
        return [self._to_out(p) for p in rows], total

    def summary_for_vendor(self, vendor_id: uuid.UUID) -> dict:
        return self.repo.summary_for_vendor(vendor_id)


class FreightPaymentService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = FreightPaymentRepository(session)

    def _to_out(self, row) -> dict:
        return {
            "id": row.id, "direction": row.direction.value, "linked_type": row.linked_type.value, "linked_id": row.linked_id,
            "transporter": row.transporter, "payer": row.payer.value, "base_freight": float(row.base_freight),
            "gst_on_freight": float(row.gst_on_freight), "tds_amount": float(row.tds_amount),
            "net_payable_to_transporter": float(row.net_payable_to_transporter),
            "final_liability_amount": float(row.final_liability_amount), "status": row.status.value,
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        rows, total = self.repo.list_for_vendor(vendor_id, params, status)
        return [self._to_out(r) for r in rows], total

    def get_for_vendor(self, vendor_id: uuid.UUID, freight_payment_id: uuid.UUID) -> dict:
        row = self.repo.get_for_vendor(vendor_id, freight_payment_id)
        if not row:
            raise NotFoundException("Freight payment not found")
        return self._to_out(row)

    def mark_paid(self, freight_payment_id: uuid.UUID) -> dict:
        row = self.repo.get_by_id(freight_payment_id)
        if not row:
            raise NotFoundException("Freight payment not found")
        if row.status.value not in ("Pending", "Approved"):
            raise ConflictException(f"Cannot mark a freight payment with status '{row.status.value}' as paid")
        row.status = "Paid"
        row.paid_on = datetime.now(timezone.utc)
        self.session.commit()
        return self._to_out(row)
