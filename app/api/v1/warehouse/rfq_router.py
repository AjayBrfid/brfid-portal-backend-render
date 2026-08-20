from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.vendor import get_rfq_service
from app.models.user import User
from app.models.vendor import Vendor
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import SelectVendorRequest
from app.services.vendor.rfq_service import RfqService

router = APIRouter(prefix="/rfqs", tags=["warehouse-rfqs"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_rfqs(search: str | None = None, status: str | None = None, params: PaginationParams = Depends(), service: RfqService = Depends(get_rfq_service), user: User = Depends(_portal)):
    items, total = service.list_rfqs(user.entity_id, params, search, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/eligible-vendors/{sku_code}", response_model=ApiResponse[list[dict]])
def get_eligible_vendors(sku_code: str, service: RfqService = Depends(get_rfq_service), user: User = Depends(_portal)):
    # The frontend passes the human-readable SKU/variant code (e.g. "SKU-76F6BE96-green-XL"),
    # not the variant's UUID — resolve it here rather than in the service, since
    # get_supplying_vendor_eligibility's other caller (store_return_service.py) already has
    # the real sku_variant_id UUID in hand and must keep passing that directly.
    variant = CatalogRepository(service.session).get_variant_by_code(sku_code)
    if not variant:
        raise NotFoundException(f"SKU '{sku_code}' not found")
    return ApiResponse(data=service.get_supplying_vendor_eligibility(user.entity_id, variant.id))


@router.get("/{rfq_id}", response_model=ApiResponse[dict])
def get_rfq(rfq_id: str, service: RfqService = Depends(get_rfq_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_rfq_detail(user.entity_id, rfq_id))


@router.get("/{rfq_id}/quotations", response_model=ApiResponse[list[dict]])
def list_quotations(rfq_id: str, service: RfqService = Depends(get_rfq_service), user: User = Depends(_portal)):
    # WhRfqDetail.jsx's per-vendor quotation cards read vendor_name, tax_percent,
    # discount_percent, lead_time_days, valid_until, and submitted_at — none of which this
    # endpoint used to return (it only sent id/vendor_id/unit_price/total_amount/delivery_days/
    # status), so every one of those fields rendered blank/undefined on that screen. `has_pdf`
    # likewise tells the comparison screen whether the vendor attached a quotation document at
    # all — the file itself is served separately (see get_quotation_pdf) since it's a redirect
    # response, not JSON.
    quotations = service.list_quotations(user.entity_id, rfq_id)
    vendor_ids = {q.vendor_id for q in quotations}
    vendors = {v.id: v for v in service.session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars()} if vendor_ids else {}
    return ApiResponse(data=[
        {
            "id": q.id, "vendor_id": q.vendor_id, "vendor_name": vendors[q.vendor_id].name if q.vendor_id in vendors else None,
            "unit_price": float(q.unit_price), "tax_percent": float(q.tax_percent), "discount_percent": float(q.discount_percent),
            "total_amount": float(q.total_amount), "lead_time_days": q.delivery_days,
            # validity_days is a duration ("valid for 30 days from submission"), not a date —
            # compute the actual deadline the UI wants to display.
            "valid_until": (q.submitted_date.date() + timedelta(days=q.validity_days)).isoformat(),
            "submitted_at": q.submitted_date, "status": q.status.value, "has_pdf": bool(q.pdf_url),
        }
        for q in quotations
    ])


@router.get("/{rfq_id}/quotations/{quotation_id}/pdf")
def get_quotation_pdf(rfq_id: str, quotation_id: str, service: RfqService = Depends(get_rfq_service), user: User = Depends(_portal)):
    from app.compat.vendor.common import redirect_to_file
    from app.repositories.procurement_repository import QuotationRepository

    service.get_rfq(user.entity_id, rfq_id)  # 404s if this RFQ isn't this warehouse's
    quotation = QuotationRepository(service.session).get_by_id(quotation_id)
    if not quotation or str(quotation.rfq_id) != rfq_id:
        raise NotFoundException("Quotation not found for this RFQ")
    return redirect_to_file(quotation.pdf_url)


@router.post("/{rfq_id}/select-vendor", response_model=ApiResponse[dict])
def select_vendor(rfq_id: str, body: SelectVendorRequest, service: RfqService = Depends(get_rfq_service), user: User = Depends(_portal)):
    po = service.select_vendor(user.entity_id, rfq_id, body.quotation_id, user_id=user.id)
    vendor = service.session.get(Vendor, po.vendor_id)
    return ApiResponse(data={"po_id": po.id, "ref_code": po.ref_code, "vendor_name": vendor.name if vendor else None, "status": po.status.value})
