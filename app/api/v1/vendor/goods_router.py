from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_goods_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import GoodsCreateRequest, GoodsUpdateRequest
from app.services.vendor.goods_service import GoodsService

router = APIRouter(prefix="/goods", tags=["vendor-goods"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_goods(params: PaginationParams = Depends(), service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.post("", response_model=ApiResponse[dict], status_code=201)
def create_goods(body: GoodsCreateRequest, service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.create(vendor.id, body.name, body.category, body.unit, body.quantity, body.price, body.gst_rate))


@router.patch("/{good_id}", response_model=ApiResponse[dict])
def update_goods(good_id: str, body: GoodsUpdateRequest, service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.update(vendor.id, good_id, **body.model_dump()))


@router.delete("/{good_id}", status_code=204)
def delete_goods(good_id: str, service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    service.delete(vendor.id, good_id)
