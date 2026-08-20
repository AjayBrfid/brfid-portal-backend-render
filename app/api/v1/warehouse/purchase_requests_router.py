from datetime import date

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_purchase_request_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.warehouse.warehouse_schemas import RaiseRfqRequest, SplitFulfilRequest
from app.services.warehouse.purchase_request_service import PurchaseRequestService

router = APIRouter(prefix="/purchase-requests", tags=["warehouse-purchase-requests"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_purchase_requests(
    search: str | None = None, status: str | None = None, date_from: date | None = None, date_to: date | None = None,
    params: PaginationParams = Depends(), service: PurchaseRequestService = Depends(get_purchase_request_service), user: User = Depends(_portal),
):
    items, total = service.list_purchase_requests(user.entity_id, params, search, status, date_from, date_to)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{ref}", response_model=ApiResponse[dict])
def get_pr(ref: str, service: PurchaseRequestService = Depends(get_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_pr_detail(user.entity_id, ref))


@router.post("/{ref}/fulfil-from-stock", response_model=ApiResponse[dict])
def fulfil_from_stock(ref: str, service: PurchaseRequestService = Depends(get_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.fulfil_from_stock(user.entity_id, ref, user_id=user.id))


@router.post("/{ref}/split-fulfil", response_model=ApiResponse[dict])
def split_fulfil(ref: str, body: SplitFulfilRequest, service: PurchaseRequestService = Depends(get_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.split_fulfil(user.entity_id, ref, body.invited_vendor_ids, user_id=user.id))


@router.post("/{ref}/raise-rfq", response_model=ApiResponse[dict])
def raise_rfq(ref: str, body: RaiseRfqRequest, service: PurchaseRequestService = Depends(get_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.raise_rfq(user.entity_id, ref, body.invited_vendor_ids, user_id=user.id))
