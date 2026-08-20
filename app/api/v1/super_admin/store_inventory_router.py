from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.super_admin import get_admin_store_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.super_admin.store_admin_service import AdminStoreService

router = APIRouter(prefix="/store-inventory", tags=["super-admin-store-inventory"])
_portal = require_portal("super_admin")


@router.get("", response_model=ApiResponse[list[dict]])
def list_store_inventory(
    store_id: str, params: PaginationParams = Depends(),
    service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal),
):
    items, total = service.list_store_inventory(store_id, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))
