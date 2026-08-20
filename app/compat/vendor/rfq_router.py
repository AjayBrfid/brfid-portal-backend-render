"""RFQ compat -- confirmed against src/pages/RfqsPage.jsx (not the stale API_SPECIFICATION.md):
the real frontend now consumes the native RfqStatus enum values verbatim ("Sent", "Awaiting
Quotations", ... "Closed") and expects a nested `skuVariant: {styleCode, name, colour, size}`
object plus a computed `quotationSubmitted` flag -- none of which the real
app/api/v1/vendor/rfq_router.py's flat {sku, product} shape provides. This reuses the exact same
RfqRepository/RfqService already wired for the real vendor RFQ routes; it only adds the
skuVariant/quotationSubmitted enrichment reads (not new business logic) on top.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.compat.vendor.common import envelope, iso, paginate_list, vendor_meta
from app.core.exceptions import NotFoundException
from app.dependencies.vendor import get_current_vendor, get_rfq_service
from app.models.catalog import Sku, SkuVariant
from app.models.procurement import Quotation, Rfq
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.rfq_service import RfqService

router = APIRouter(tags=["vendor-compat-rfqs"])

_ALL = PaginationParams(page=1, limit=100000)


def _sku_variant_out(session, sku_variant_id):
    if not sku_variant_id:
        return None
    variant = session.get(SkuVariant, sku_variant_id)
    if not variant:
        return None
    sku = session.get(Sku, variant.sku_id)
    return {"styleCode": sku.style_code if sku else None, "name": sku.name if sku else None, "colour": variant.colour, "size": variant.size}


def _quotation_submitted(session, rfq_id, vendor_id) -> bool:
    stmt = select(Quotation.id).where(Quotation.rfq_id == rfq_id, Quotation.vendor_id == vendor_id).limit(1)
    return session.execute(stmt).scalar_one_or_none() is not None


def _rfq_out(session, rfq: Rfq, vendor_id) -> dict:
    return {
        "id": str(rfq.id),
        "refCode": rfq.ref_code,
        "quantity": rfq.quantity,
        "unit": rfq.unit,
        "issueDate": iso(rfq.issue_date),
        "closingDate": iso(rfq.closing_date),
        "requiredDeliveryDate": iso(rfq.required_delivery_date),
        "status": rfq.status.value,
        "createdAt": iso(rfq.created_at),
        "skuVariant": _sku_variant_out(session, rfq.sku_variant_id),
        "quotationSubmitted": _quotation_submitted(session, rfq.id, vendor_id),
        "attachments": [],  # genuine gap: no RfqAttachment model in the unified backend
    }


@router.get("/rfqs")
def list_rfqs(
    page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, category: str | None = None,
    service: RfqService = Depends(get_rfq_service), vendor: Vendor = Depends(get_current_vendor),
):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, status)
    items = [_rfq_out(service.session, r, vendor.id) for r in rows]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["refCode"] or "").lower()]
    # `category` has no backing column on Rfq (it lives on the underlying Sku, one query away
    # per row) -- filter on the nested skuVariant's style code as the closest practical proxy.
    if category:
        items = [i for i in items if i["skuVariant"] and category.lower() in (i["skuVariant"].get("name") or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/rfqs/{rfq_id}")
def get_rfq(rfq_id: str, service: RfqService = Depends(get_rfq_service), vendor: Vendor = Depends(get_current_vendor)):
    rfq = service.get_rfq_for_vendor(vendor.id, rfq_id)
    return envelope(_rfq_out(service.session, rfq, vendor.id))


@router.get("/rfqs/{rfq_id}/attachments/{attachment_id}")
def get_rfq_attachment(rfq_id: str, attachment_id: str, service: RfqService = Depends(get_rfq_service), vendor: Vendor = Depends(get_current_vendor)):
    service.get_rfq_for_vendor(vendor.id, rfq_id)  # 404s if not this vendor's RFQ
    raise NotFoundException("Attachment not found")
