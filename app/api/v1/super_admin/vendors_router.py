from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.super_admin import get_admin_vendor_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import GenerateSkuRequest, RejectRequest, SetPasswordRequest
from app.services.super_admin.vendor_admin_service import AdminVendorService

router = APIRouter(prefix="/vendors", tags=["super-admin-vendors"])
_portal = require_portal("super_admin")


@router.get("", response_model=ApiResponse[list[dict]])
def list_vendors(
    search: str | None = None, status: str | None = None, sort: str | None = None, order: str | None = None,
    params: PaginationParams = Depends(), service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal),
):
    items, total = service.list_vendors(params, search, status, sort, order)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def vendor_stats(service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.stats())


@router.get("/{vendor_id}", response_model=ApiResponse[dict])
def get_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.get_vendor(vendor_id))


@router.post("/{vendor_id}/approve", response_model=ApiResponse[dict])
def approve_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.approve(vendor_id, admin))


@router.post("/{vendor_id}/reject", response_model=ApiResponse[dict])
def reject_vendor(vendor_id: str, body: RejectRequest, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.reject(vendor_id, admin, body.reason))


@router.post("/{vendor_id}/block", response_model=ApiResponse[dict])
def block_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.block(vendor_id, admin))


@router.post("/{vendor_id}/unblock", response_model=ApiResponse[dict])
def unblock_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.unblock(vendor_id, admin))


@router.put("/{vendor_id}/password", response_model=ApiResponse[dict])
def set_vendor_password(vendor_id: str, body: SetPasswordRequest, service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    service.set_vendor_password(vendor_id, body.new_password)
    return ApiResponse(data={"success": True})
