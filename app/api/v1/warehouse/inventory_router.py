from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_inventory_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.warehouse.warehouse_schemas import AdjustInventoryRequest
from app.services.warehouse.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["warehouse-inventory"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_inventory(
    search: str | None = None, category: str | None = None, status: str | None = None,
    params: PaginationParams = Depends(), service: InventoryService = Depends(get_inventory_service), user: User = Depends(_portal),
):
    items, total = service.list_inventory(user.entity_id, params, search, category, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/reserved", response_model=ApiResponse[list[dict]])
def list_reserved(params: PaginationParams = Depends(), service: InventoryService = Depends(get_inventory_service), user: User = Depends(_portal)):
    items, total = service.list_reserved(user.entity_id, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/style/{style_code}", response_model=ApiResponse[dict])
def get_style_stock(style_code: str, service: InventoryService = Depends(get_inventory_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_style_stock(user.entity_id, style_code))


@router.get("/{sku}", response_model=ApiResponse[dict])
def get_inventory(sku: str, service: InventoryService = Depends(get_inventory_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_inventory_detail(user.entity_id, sku))


@router.patch("/{sku}/adjust", response_model=ApiResponse[dict])
def adjust_inventory(sku: str, body: AdjustInventoryRequest, service: InventoryService = Depends(get_inventory_service), user: User = Depends(_portal)):
    service.adjust_inventory(user.entity_id, sku, body.on_hand_delta, body.available_delta)
    return ApiResponse(data=service.get_inventory_detail(user.entity_id, sku))
