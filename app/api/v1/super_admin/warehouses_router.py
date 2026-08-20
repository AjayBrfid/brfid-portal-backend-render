import uuid

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.super_admin import get_admin_warehouse_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.warehouse.warehouse_schemas import RejectRequest
from app.services.super_admin.warehouse_admin_service import AdminWarehouseService

router = APIRouter(prefix="/warehouses", tags=["super-admin-warehouses"])
_portal = require_portal("super_admin")


@router.get("", response_model=ApiResponse[list[dict]])
def list_warehouses(
    search: str | None = None, status: str | None = None, params: PaginationParams = Depends(),
    service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal),
):
    items, total = service.list_warehouses(params, search, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def warehouse_stats(service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.stats())


@router.get("/{warehouse_id}", response_model=ApiResponse[dict])
def get_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.get_warehouse(warehouse_id))


@router.post("/{warehouse_id}/approve", response_model=ApiResponse[dict])
def approve_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.approve(warehouse_id, admin))


@router.post("/{warehouse_id}/reject", response_model=ApiResponse[dict])
def reject_warehouse(warehouse_id: str, body: RejectRequest, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.reject(warehouse_id, admin, body.reason))


@router.post("/{warehouse_id}/block", response_model=ApiResponse[dict])
def block_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.block(warehouse_id, admin))


@router.post("/{warehouse_id}/unblock", response_model=ApiResponse[dict])
def unblock_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.unblock(warehouse_id, admin))


@router.get("/{warehouse_id}/zones", response_model=ApiResponse[list[dict]])
def list_warehouse_zones(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.list_zones(warehouse_id))


@router.get("/{warehouse_id}/movements", response_model=ApiResponse[list[dict]])
def list_warehouse_movements(
    warehouse_id: str, search: str | None = None, params: PaginationParams = Depends(),
    service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal),
):
    items, total = service.list_movements(warehouse_id, search, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))
