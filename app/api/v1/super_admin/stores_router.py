from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.super_admin import get_admin_store_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.warehouse.warehouse_schemas import RejectRequest
from app.services.super_admin.store_admin_service import AdminStoreService

router = APIRouter(prefix="/stores", tags=["super-admin-stores"])
_portal = require_portal("super_admin")


@router.get("", response_model=ApiResponse[list[dict]])
def list_stores(
    search: str | None = None, status: str | None = None, params: PaginationParams = Depends(),
    service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal),
):
    items, total = service.list_stores(params, search, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def store_stats(service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.stats())


@router.get("/{store_id}", response_model=ApiResponse[dict])
def get_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.get_store(store_id))


@router.post("/{store_id}/approve", response_model=ApiResponse[dict])
def approve_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.approve(store_id, admin))


@router.post("/{store_id}/reject", response_model=ApiResponse[dict])
def reject_store(store_id: str, body: RejectRequest, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.reject(store_id, admin, body.reason))


@router.post("/{store_id}/block", response_model=ApiResponse[dict])
def block_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.block(store_id, admin))


@router.post("/{store_id}/unblock", response_model=ApiResponse[dict])
def unblock_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.unblock(store_id, admin))
