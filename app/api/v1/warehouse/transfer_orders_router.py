from datetime import date

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_transfer_order_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.warehouse.warehouse_schemas import DispatchRequest, UpdateTransferStatusRequest
from app.services.warehouse.transfer_order_service import TransferOrderService

router = APIRouter(prefix="/transfer-orders", tags=["warehouse-transfer-orders"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_transfer_orders(
    search: str | None = None, status: str | None = None, source_type: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    params: PaginationParams = Depends(), service: TransferOrderService = Depends(get_transfer_order_service), user: User = Depends(_portal),
):
    items, total = service.list_transfer_orders(user.entity_id, params, search, status, source_type, date_from, date_to)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{to_id}", response_model=ApiResponse[dict])
def get_transfer_order(to_id: str, service: TransferOrderService = Depends(get_transfer_order_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_transfer_order_detail(user.entity_id, to_id))


@router.post("/{to_id}/dispatch", response_model=ApiResponse[dict])
def dispatch(to_id: str, body: DispatchRequest, service: TransferOrderService = Depends(get_transfer_order_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.dispatch_transfer_order(user.entity_id, to_id, body.transporter, body.vehicle_number, body.tracking_number, body.packages, body.remarks))


@router.patch("/{to_id}/status", response_model=ApiResponse[dict])
def update_status(to_id: str, body: UpdateTransferStatusRequest, service: TransferOrderService = Depends(get_transfer_order_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.update_status(user.entity_id, to_id, body.status))
