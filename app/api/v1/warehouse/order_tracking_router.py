from datetime import date

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_purchase_request_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.warehouse.purchase_request_service import PurchaseRequestService

router = APIRouter(prefix="/order-tracking", tags=["warehouse-order-tracking"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_order_tracking(
    search: str | None = None, status: str | None = None, date_from: date | None = None, date_to: date | None = None,
    params: PaginationParams = Depends(), service: PurchaseRequestService = Depends(get_purchase_request_service), user: User = Depends(_portal),
):
    items, total = service.list_order_tracking(user.entity_id, params, search, status, date_from, date_to)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))
