from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.super_admin import get_admin_vendor_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import GenerateSkuRequest
from app.services.super_admin.vendor_admin_service import AdminVendorService

vendor_stock_router = APIRouter(prefix="/vendor-stock", tags=["super-admin-vendor-stock"])
_portal = require_portal("super_admin")


@vendor_stock_router.get("", response_model=ApiResponse[list[dict]])
def list_vendor_stock(search: str | None = None, params: PaginationParams = Depends(), service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    items, total = service.list_vendor_stock(params, search)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


vendor_catalog_router = APIRouter(prefix="/vendor-catalog", tags=["super-admin-vendor-catalog"])


@vendor_catalog_router.get("", response_model=ApiResponse[list[dict]])
def list_vendor_catalog(search: str | None = None, status: str | None = None, params: PaginationParams = Depends(), service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    items, total = service.list_vendor_catalog(params, search, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@vendor_catalog_router.get("/{submission_id}", response_model=ApiResponse[dict])
def get_vendor_catalog(submission_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    row = service.get_vendor_catalog_submission(submission_id)
    return ApiResponse(data={"id": row.id, "name": row.name, "vendor_id": row.vendor_id, "status": row.status.value})


@vendor_catalog_router.post("/{submission_id}/generate-sku", response_model=ApiResponse[dict])
def generate_sku(submission_id: str, body: GenerateSkuRequest, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.generate_sku(submission_id, admin, body.style_code, body.hsn, body.gst_rate, body.mrp))
