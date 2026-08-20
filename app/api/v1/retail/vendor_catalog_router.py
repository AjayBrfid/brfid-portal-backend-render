from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.catalog import get_master_catalog_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.catalog_service import MasterCatalogService

router = APIRouter(prefix="/vendor-catalog", tags=["retail-vendor-catalog"])
_portal = require_portal("store")


@router.get("", response_model=ApiResponse[list[dict]])
def list_vendor_catalogue(
    search: str | None = None, q: str | None = None, type: str | None = None, gender: str | None = None,
    params: PaginationParams = Depends(), service: MasterCatalogService = Depends(get_master_catalog_service), _: User = Depends(_portal),
):
    items, total = service.list_catalogue(params, q or search, type, gender, None)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/types", response_model=ApiResponse[list[str]])
def list_types(service: MasterCatalogService = Depends(get_master_catalog_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.list_types())


@router.get("/genders", response_model=ApiResponse[list[str]])
def list_genders(service: MasterCatalogService = Depends(get_master_catalog_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.list_genders())


@router.get("/vendors", response_model=ApiResponse[list[dict]])
def list_vendors(service: MasterCatalogService = Depends(get_master_catalog_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.list_supplying_vendors())
