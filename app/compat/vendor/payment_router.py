"""Goods payments compat (Payments page's "Goods Payments" tab -- distinct from
freight_payment_router.py's freight/transport payments). Confirmed against
src/pages/PaymentsPage.jsx: reuses the exact same PaymentService already wired for the real
`/api/v1/vendor/payments` routes, just resolving invoice/PO codes and reshaping field names.
`remittance-advice` is a genuine gap -- no PDF generation exists anywhere in this backend (same
conclusion the purchase-orders compat router reached for `/export`), so it 404s until a real
document is stored for a payment. `statement` degrades to CSV bytes under the requested
filename (no xlsx library at the time this was written), but now actually honors the requested
date range -- see list_for_vendor's date_from/date_to below. The frontend sends camelCase
`startDate`/`endDate` query params (services/api/payments.js), so these are bound via an
explicit alias rather than FastAPI's default snake_case-only matching.
"""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.compat.vendor.common import dec, envelope, iso, paginate_list, redirect_to_file, vendor_meta
from app.core.exceptions import BadRequestException
from app.dependencies.vendor import get_current_vendor, get_payment_service
from app.models.procurement import PurchaseOrder
from app.models.shipping import Invoice
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["vendor-compat-payments"])

_ALL = PaginationParams(page=1, limit=100000)
_STATUS_KEYS = ("Paid", "Pending", "Overdue", "Processing")


def _payment_out(session, payment) -> dict:
    invoice = session.get(Invoice, payment.invoice_id)
    po = session.get(PurchaseOrder, payment.po_id)
    return {
        "id": str(payment.id),
        "invoiceId": invoice.invoice_number if invoice else None,
        "poId": po.ref_code if po else None,
        "invoiceDate": iso(invoice.invoice_date) if invoice else None,
        "dueDate": iso(invoice.due_date) if invoice else None,
        "amount": dec(payment.amount),
        "status": payment.status.value,
        "paidDate": iso(payment.paid_date),
        "paymentMode": payment.payment_mode.value if payment.payment_mode else None,
        "referenceNo": payment.reference_no,
    }


@router.get("")
def list_payments(
    page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, period: str | None = None,
    service: PaymentService = Depends(get_payment_service), vendor: Vendor = Depends(get_current_vendor),
):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL)
    items = [_payment_out(service.session, p) for p in rows]
    if status:
        items = [i for i in items if i["status"] == status]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["invoiceId"] or "").lower() or q in (i["poId"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/summary")
def get_payments_summary(period: str | None = None, service: PaymentService = Depends(get_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    counts = service.summary_for_vendor(vendor.id)
    total_invoiced = sum(v["amount"] for v in counts.values())
    return envelope({
        "totalInvoiced": total_invoiced,
        "totalPaid": counts.get("Paid", {}).get("amount", 0.0),
        "pending": counts.get("Pending", {}).get("amount", 0.0),
        "overdue": counts.get("Overdue", {}).get("amount", 0.0),
    })


@router.get("/{payment_id}/remittance-advice")
def download_remittance_advice(payment_id: str, service: PaymentService = Depends(get_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL)
    if not any(str(p.id) == payment_id for p in rows):
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Payment not found")
    # Genuine gap: no remittance-advice document is ever generated/stored for a payment.
    return redirect_to_file(None)


@router.get("/statement")
def export_payment_statement(
    start_date: date | None = Query(None, alias="startDate"), end_date: date | None = Query(None, alias="endDate"),
    service: PaymentService = Depends(get_payment_service), vendor: Vendor = Depends(get_current_vendor),
):
    if start_date and end_date and start_date > end_date:
        raise BadRequestException("'startDate' must be on or before 'endDate'")
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, start_date, end_date)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Invoice No.", "PO Number", "Amount", "Status", "Paid Date"])
    for p in rows:
        out = _payment_out(service.session, p)
        writer.writerow([out["invoiceId"], out["poId"], out["amount"], out["status"], out["paidDate"]])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=payment-statement.csv"})
