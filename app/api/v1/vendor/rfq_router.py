from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_rfq_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.vendor.rfq_service import RfqService

router = APIRouter(prefix="/rfqs", tags=["vendor-rfqs"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_rfqs(status: str | None = None, params: PaginationParams = Depends(), service: RfqService = Depends(get_rfq_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_rfqs_for_vendor(vendor.id, params, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{rfq_id}", response_model=ApiResponse[dict])
def get_rfq(rfq_id: str, service: RfqService = Depends(get_rfq_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.get_rfq_detail_for_vendor(vendor.id, rfq_id))
