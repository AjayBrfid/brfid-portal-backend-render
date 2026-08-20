from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_retail_store_return_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.retail.store_return_service import StoreReturnService

# Replenishment.jsx has always called GET /replenishments (a store's own StoreReturn requests —
# see StoreReturnService's own module docstring) but no router ever exposed that path, so every
# request 404'd and the whole "Replenishment & Write-off" screen looked permanently broken.
router = APIRouter(prefix="/replenishments", tags=["retail-replenishments"])
_portal = require_portal("store")


@router.get("", response_model=ApiResponse[list[dict]])
def list_replenishments(
    q: str | None = None, params: PaginationParams = Depends(),
    service: StoreReturnService = Depends(get_retail_store_return_service), user: User = Depends(_portal),
):
    items, total = service.list_for_store(user.entity_id, params, q)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{ref}", response_model=ApiResponse[dict])
def get_replenishment(ref: str, service: StoreReturnService = Depends(get_retail_store_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.to_out(service.get_for_store(user.entity_id, ref)))


@router.get("/{ref}/tracking", response_model=ApiResponse[dict])
def get_replenishment_tracking(ref: str, service: StoreReturnService = Depends(get_retail_store_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_tracking_for_store(user.entity_id, ref))
