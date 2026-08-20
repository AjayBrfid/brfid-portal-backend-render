from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_warehouse_store_return_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.warehouse.store_return_service import WarehouseStoreReturnService

router = APIRouter(prefix="/returns/store", tags=["warehouse-store-returns"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_returns(
    search: str | None = None, decision: str | None = None, status: str | None = None,
    params: PaginationParams = Depends(), service: WarehouseStoreReturnService = Depends(get_warehouse_store_return_service), user: User = Depends(_portal),
):
    items, total = service.list_store_returns(user.entity_id, params, search, decision, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{ref}", response_model=ApiResponse[dict])
def get_return(ref: str, service: WarehouseStoreReturnService = Depends(get_warehouse_store_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_store_return_detail(user.entity_id, ref))


@router.post("/{ref}/resolve", response_model=ApiResponse[dict])
def resolve_return(ref: str, service: WarehouseStoreReturnService = Depends(get_warehouse_store_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.resolve_return(user.entity_id, ref, user_id=user.id))
