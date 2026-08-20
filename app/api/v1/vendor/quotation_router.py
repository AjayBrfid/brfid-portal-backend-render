from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.dependencies.vendor import get_current_vendor, get_quotation_service
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import SubmitQuotationRequest
from app.services.vendor.quotation_service import QuotationService

router = APIRouter(tags=["vendor-quotations"])


def _to_out(q) -> dict:
    return {
        "id": q.id, "code": q.code, "rfq_id": q.rfq_id, "unit_price": float(q.unit_price), "tax_percent": float(q.tax_percent),
        "discount_percent": float(q.discount_percent), "total_amount": float(q.total_amount), "delivery_days": q.delivery_days,
        "status": q.status.value, "submitted_date": q.submitted_date,
    }


@router.post("/rfqs/{rfq_id}/quotations", response_model=ApiResponse[dict], status_code=201)
def submit_quotation(
    rfq_id: str, body: SubmitQuotationRequest, service: QuotationService = Depends(get_quotation_service),
    vendor: Vendor = Depends(get_current_vendor), user: User = Depends(get_current_user),
):
    quotation = service.submit_quotation(
        vendor.id, rfq_id, body.unit_price, body.tax_percent, body.discount_percent, body.delivery_days,
        body.warranty, body.payment_terms, body.remarks, body.validity_days, body.freight_payer, body.freight_details_json,
        user.id,
    )
    return ApiResponse(data=_to_out(quotation))


@router.get("/quotations", response_model=ApiResponse[list[dict]])
def list_quotations(params: PaginationParams = Depends(), service: QuotationService = Depends(get_quotation_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params)
    return ApiResponse(data=[_to_out(q) for q in items], meta=build_meta(params.page, params.limit, total))


@router.get("/quotations/{quotation_id}", response_model=ApiResponse[dict])
def get_quotation(quotation_id: str, service: QuotationService = Depends(get_quotation_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=_to_out(service.get_for_vendor(vendor.id, quotation_id)))
