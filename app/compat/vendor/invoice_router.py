"""Invoices compat. Corrected ground truth (coordinator + direct read of
src/services/api/invoices.js / src/pages/InvoicesPage.jsx): `upload` posts poId/asnId(optional)/
invoiceNumber/invoiceDate/baseAmount/gstAmount/file -- matching the real `invoices` table columns
directly (base_amount/gst_amount), not the spec doc's amount/gst shape. Status is consumed
lowercase (pending|accepted|rejected), which is exactly InvoiceService's native InvoiceStatus
value -- no remapping needed, just camelCase field names.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.compat.vendor.common import envelope, paginate_list, redirect_to_file, vendor_meta
from app.dependencies.vendor import get_current_vendor, get_invoice_service
from app.models.procurement import PurchaseOrder
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.invoice_service import InvoiceService
from app.utils.storage import get_storage_client

router = APIRouter(prefix="/invoices", tags=["vendor-compat-invoices"])

_ALL = PaginationParams(page=1, limit=100000)


def _invoice_out(session, service: InvoiceService, invoice) -> dict:
    data = service.to_out(invoice)
    po = session.get(PurchaseOrder, invoice.po_id)
    return {
        "id": str(data["id"]),
        "poId": str(data["po_id"]),
        "poRefCode": po.ref_code if po else None,
        "asnId": str(invoice.asn_id) if invoice.asn_id else None,
        "invoiceNumber": data["invoice_number"],
        "invoiceDate": data["invoice_date"].isoformat() if data["invoice_date"] else None,
        "dueDate": data["due_date"].isoformat() if data["due_date"] else None,
        "baseAmount": data["base_amount"],
        "gstAmount": data["gst_amount"],
        "discountAmount": data["discount_amount"],
        "freightAmount": data["freight_amount"],
        "totalAmount": data["total_amount"],
        "status": data["status"],
        "pdfUrl": data["pdf_url"],
    }


@router.get("")
def list_invoices(page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, service: InvoiceService = Depends(get_invoice_service), vendor: Vendor = Depends(get_current_vendor)):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, status)
    items = [_invoice_out(service.session, service, i) for i in rows]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["invoiceNumber"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, service: InvoiceService = Depends(get_invoice_service), vendor: Vendor = Depends(get_current_vendor)):
    invoice = service.get_for_vendor(vendor.id, invoice_id)
    return envelope(_invoice_out(service.session, service, invoice))


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, service: InvoiceService = Depends(get_invoice_service), vendor: Vendor = Depends(get_current_vendor)):
    invoice = service.get_for_vendor(vendor.id, invoice_id)
    return redirect_to_file(invoice.pdf_url)


@router.post("", status_code=201)
def upload_invoice(
    po_id: str = Form(..., alias="poId"),
    asn_id: str | None = Form(None, alias="asnId"),
    invoice_number: str = Form(..., alias="invoiceNumber"),
    invoice_date: str = Form(..., alias="invoiceDate"),
    base_amount: float = Form(..., alias="baseAmount"),
    gst_amount: float = Form(..., alias="gstAmount"),
    file: UploadFile | None = File(None),
    service: InvoiceService = Depends(get_invoice_service),
    vendor: Vendor = Depends(get_current_vendor),
):
    invoice = service.create_invoice(
        vendor.id, po_id, asn_id or None, invoice_number, datetime.strptime(invoice_date, "%Y-%m-%d").date(),
        None, Decimal(str(base_amount)), Decimal(str(gst_amount)), Decimal("0"), Decimal("0"),
    )
    if file is not None:
        uploaded = get_storage_client().save(file, folder="vendor-invoices")
        invoice.pdf_url = uploaded.url
        service.session.commit()
    return envelope(_invoice_out(service.session, service, invoice))
