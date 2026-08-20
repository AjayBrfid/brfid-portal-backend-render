from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_payment_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.vendor.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["vendor-payments"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_payments(params: PaginationParams = Depends(), service: PaymentService = Depends(get_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/summary", response_model=ApiResponse[dict])
def payment_summary(service: PaymentService = Depends(get_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.summary_for_vendor(vendor.id))
