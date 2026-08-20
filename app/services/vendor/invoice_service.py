import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.payment import Payment, PaymentStatus
from app.models.shipping import Invoice
from app.repositories.shipping_repository import InvoiceRepository
from app.repositories.procurement_repository import PurchaseOrderRepository
from app.utils.pagination import PaginationParams


class InvoiceService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = InvoiceRepository(session)
        self.pos = PurchaseOrderRepository(session)

    def create_invoice(
        self, vendor_id: uuid.UUID, po_id: uuid.UUID, asn_id: uuid.UUID | None, invoice_number: str,
        invoice_date: date, due_date: date | None, base_amount: Decimal, gst_amount: Decimal,
        discount_amount: Decimal, freight_amount: Decimal,
    ) -> Invoice:
        po = self.pos.get_for_vendor(vendor_id, po_id)
        if not po:
            raise NotFoundException("Purchase order not found")
        total_amount = base_amount + gst_amount + freight_amount - discount_amount
        invoice = self.repo.add(
            Invoice(
                po_id=po_id, asn_id=asn_id, vendor_id=vendor_id, invoice_number=invoice_number, invoice_date=invoice_date,
                due_date=due_date, base_amount=base_amount, gst_amount=gst_amount, discount_amount=discount_amount,
                freight_amount=freight_amount, total_amount=round(total_amount, 2), status="pending",
            )
        )
        self.session.commit()
        return invoice

    def _payment_for(self, invoice_id: uuid.UUID) -> Payment | None:
        return self.session.execute(select(Payment).where(Payment.invoice_id == invoice_id)).scalar_one_or_none()

    def to_out(self, invoice: Invoice) -> dict:
        payment = self._payment_for(invoice.id)
        return {
            "id": invoice.id, "po_id": invoice.po_id, "asn_id": invoice.asn_id, "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date, "due_date": invoice.due_date, "base_amount": float(invoice.base_amount),
            "gst_amount": float(invoice.gst_amount), "discount_amount": float(invoice.discount_amount),
            "freight_amount": float(invoice.freight_amount), "total_amount": float(invoice.total_amount),
            "status": invoice.status.value, "pdf_url": invoice.pdf_url,
            "paid": payment is not None and payment.status == PaymentStatus.PAID,
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        rows, total = self.repo.list_for_vendor(vendor_id, params, status)
        return [self.to_out(i) for i in rows], total

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, status: str | None = None, po_id: uuid.UUID | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, status, po_id)
        return [self.to_out(i) for i in rows], total

    def get_for_vendor(self, vendor_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
        invoice = self.repo.get_for_vendor(vendor_id, invoice_id)
        if not invoice:
            raise NotFoundException("Invoice not found")
        return invoice

    def update_status(self, invoice_id: uuid.UUID, status: str) -> dict:
        invoice = self.repo.get_by_id(invoice_id)
        if not invoice:
            raise NotFoundException("Invoice not found")
        if invoice.status.value != "pending":
            raise ConflictException(f"Cannot update an invoice already marked '{invoice.status.value}'")
        invoice.status = status
        if status == "accepted":
            self.session.add(Payment(invoice_id=invoice.id, po_id=invoice.po_id, amount=invoice.total_amount, status="Pending"))
        self.session.commit()
        return self.to_out(invoice)

    def mark_paid(self, invoice_id: uuid.UUID) -> dict:
        """The warehouse's "Mark as Paid" action — there was never a step in this UI for the
        separate "accept this invoice" transition update_status() expects before it opens a
        Payment row, so this creates that Payment (if one doesn't already exist) and settles it
        in one action, rather than requiring two."""
        invoice = self.repo.get_by_id(invoice_id)
        if not invoice:
            raise NotFoundException("Invoice not found")
        if invoice.status.value == "rejected":
            raise ConflictException("Cannot mark a rejected invoice as paid")

        payment = self._payment_for(invoice_id)
        if not payment:
            invoice.status = "accepted"
            payment = Payment(invoice_id=invoice.id, po_id=invoice.po_id, amount=invoice.total_amount, status="Pending")
            self.session.add(payment)
            self.session.flush()
        if payment.status == PaymentStatus.PAID:
            raise ConflictException("This invoice has already been marked as paid")

        payment.status = "Paid"
        payment.paid_date = datetime.now(timezone.utc).date()
        self.session.commit()
        return self.to_out(invoice)
