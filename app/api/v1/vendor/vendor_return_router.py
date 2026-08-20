from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_vendor_return_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.vendor.vendor_return_service import VendorReturnService

router = APIRouter(prefix="/returns", tags=["vendor-returns"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_returns(status: str | None = None, params: PaginationParams = Depends(), service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{return_id}", response_model=ApiResponse[dict])
def get_return(return_id: str, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.get_for_vendor(vendor.id, return_id))


@router.patch("/{return_id}/complete", response_model=ApiResponse[dict])
def complete_return(return_id: str, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.complete(vendor.id, return_id))
