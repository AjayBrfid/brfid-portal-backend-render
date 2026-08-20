"""Quotations compat. Corrected ground truth (per coordinator + direct read of
src/services/api/quotations.js and src/pages/QuotationsPage.jsx): `submit` posts multipart with
unitPrice/taxPercent/discountPercent/deliveryDays/warranty/paymentTerms/remarks/validityDays/
freightPayer/freightDetails/file -- matching the real quotations table columns directly, not the
stale amount/gst/transportArrangement shape in API_SPECIFICATION.md. The frontend also expects a
nested `rfq: {refCode, closingDate, skuVariant}` object and native QuotationStatus
values, both built here from the same QuotationRepository/RfqRepository already used elsewhere.
"""
import json

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.compat.vendor.common import dec, envelope, iso, paginate_list, redirect_to_file, vendor_meta
from app.compat.vendor.rfq_router import _sku_variant_out
from app.core.exceptions import BadRequestException
from app.dependencies.vendor import get_current_vendor, get_quotation_service
from app.models.procurement import Quotation, Rfq
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.quotation_service import QuotationService
from app.utils.storage import get_storage_client

router = APIRouter(tags=["vendor-compat-quotations"])

_ALL = PaginationParams(page=1, limit=100000)


def _rfq_summary(session, rfq_id) -> dict | None:
    rfq = session.get(Rfq, rfq_id)
    if not rfq:
        return None
    return {
        "refCode": rfq.ref_code, "closingDate": iso(rfq.closing_date),
        "skuVariant": _sku_variant_out(session, rfq.sku_variant_id),
    }


def _quotation_out(session, q: Quotation) -> dict:
    return {
        "id": str(q.id),
        "code": q.code,
        "rfqId": str(q.rfq_id),
        "rfq": _rfq_summary(session, q.rfq_id),
        "submittedDate": iso(q.submitted_date),
        "unitPrice": dec(q.unit_price),
        "taxPercent": dec(q.tax_percent),
        "discountPercent": dec(q.discount_percent),
        "totalAmount": dec(q.total_amount),
        "deliveryDays": q.delivery_days,
        "warranty": q.warranty,
        "paymentTerms": q.payment_terms,
        "remarks": q.remarks,
        "validityDays": q.validity_days,
        "freightPayer": q.freight_payer.value,
        "freightDetails": q.freight_details_json,
        "status": q.status.value,
        "pdfUrl": q.pdf_url,
    }


@router.post("/rfqs/{rfq_id}/quotations", status_code=201)
def submit_quotation(
    rfq_id: str,
    unit_price: float = Form(..., alias="unitPrice"),
    tax_percent: float = Form(0, alias="taxPercent"),
    discount_percent: float = Form(0, alias="discountPercent"),
    delivery_days: int = Form(..., alias="deliveryDays"),
    warranty: str | None = Form(None),
    payment_terms: str | None = Form(None, alias="paymentTerms"),
    remarks: str | None = Form(None),
    validity_days: int = Form(..., alias="validityDays", ge=0),
    freight_payer: str = Form(..., alias="freightPayer"),
    freight_details: str | None = Form(None, alias="freightDetails"),
    file: UploadFile | None = File(None),
    service: QuotationService = Depends(get_quotation_service),
    vendor: Vendor = Depends(get_current_vendor),
):
    freight_details_json = None
    if freight_details:
        try:
            freight_details_json = json.loads(freight_details)
        except (json.JSONDecodeError, TypeError) as exc:
            raise BadRequestException("`freightDetails` must be valid JSON") from exc

    quotation = service.submit_quotation(
        vendor.id, rfq_id, unit_price, tax_percent, discount_percent, delivery_days, warranty,
        payment_terms, remarks, validity_days, freight_payer, freight_details_json,
    )
    if file is not None:
        uploaded = get_storage_client().save(file, folder="quotation-pdfs")
        quotation.pdf_url = uploaded.url
        service.session.commit()
    return envelope(_quotation_out(service.session, quotation))


@router.get("/quotations")
def list_quotations(page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, service: QuotationService = Depends(get_quotation_service), vendor: Vendor = Depends(get_current_vendor)):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL)
    items = [_quotation_out(service.session, q) for q in rows]
    if status:
        items = [i for i in items if i["status"] == status]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["code"] or "").lower() or q in (i["rfq"]["refCode"] if i["rfq"] else "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/quotations/{quotation_id}")
def get_quotation(quotation_id: str, service: QuotationService = Depends(get_quotation_service), vendor: Vendor = Depends(get_current_vendor)):
    quotation = service.get_for_vendor(vendor.id, quotation_id)
    return envelope(_quotation_out(service.session, quotation))


@router.get("/quotations/{quotation_id}/pdf")
def download_quotation_pdf(quotation_id: str, service: QuotationService = Depends(get_quotation_service), vendor: Vendor = Depends(get_current_vendor)):
    quotation = service.get_for_vendor(vendor.id, quotation_id)
    return redirect_to_file(quotation.pdf_url)
