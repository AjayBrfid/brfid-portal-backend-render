from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.catalog import get_master_catalog_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.catalog_service import MasterCatalogService

router = APIRouter(prefix="/skus", tags=["warehouse-catalogue"])
_portal = require_portal("warehouse")


@router.get("/catalogue", response_model=ApiResponse[list[dict]])
def list_catalogue(
    search: str | None = None, type: str | None = None, gender: str | None = None, colour: str | None = None,
    params: PaginationParams = Depends(), service: MasterCatalogService = Depends(get_master_catalog_service), _: User = Depends(_portal),
):
    items, total = service.list_catalogue(params, search, type, gender, colour)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))
