from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_retail_purchase_request_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.retail.retail_schemas import BulkCreateRequest, CreatePurchaseRequestBody
from app.services.retail.purchase_request_service import RetailPurchaseRequestService

router = APIRouter(prefix="/purchase-requests", tags=["retail-purchase-requests"])
_portal = require_portal("store")


@router.get("", response_model=ApiResponse[list[dict]])
def list_requests(
    status: str | None = None, q: str | None = None, params: PaginationParams = Depends(),
    service: RetailPurchaseRequestService = Depends(get_retail_purchase_request_service), user: User = Depends(_portal),
):
    items, total = service.list_requests(user.entity_id, params, q, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.post("", response_model=ApiResponse[dict], status_code=201)
def create_request(body: CreatePurchaseRequestBody, service: RetailPurchaseRequestService = Depends(get_retail_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.create_request(user.entity_id, body.sku, body.warehouse, body.qty, body.expected_date, user.id))


@router.post("/bulk", response_model=ApiResponse[list[dict]])
def create_bulk(body: BulkCreateRequest, service: RetailPurchaseRequestService = Depends(get_retail_purchase_request_service), user: User = Depends(_portal)):
    items = service.create_bulk(user.entity_id, body.warehouse, body.expected_date, [(i.sku, i.qty) for i in body.items], user.id)
    return ApiResponse(data=items)


@router.get("/{ref}", response_model=ApiResponse[dict])
def get_request(ref: str, service: RetailPurchaseRequestService = Depends(get_retail_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_request(user.entity_id, ref))


@router.get("/{ref}/tracking", response_model=ApiResponse[dict])
def get_tracking(ref: str, service: RetailPurchaseRequestService = Depends(get_retail_purchase_request_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_tracking(user.entity_id, ref))
