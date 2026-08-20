from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_warehouse_reports_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.warehouse.reports_service import WarehouseReportsService

router = APIRouter(prefix="/reports", tags=["warehouse-reports"])
_portal = require_portal("warehouse")


@router.get("/summary", response_model=ApiResponse[dict])
def get_summary(
    period: str = "monthly", service: WarehouseReportsService = Depends(get_warehouse_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_summary(user.entity_id, period))


@router.get("/trend", response_model=ApiResponse[dict])
def get_trend(
    period: str = "monthly", service: WarehouseReportsService = Depends(get_warehouse_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_trend(user.entity_id, period))


@router.get("/fulfilment-breakdown", response_model=ApiResponse[list[dict]])
def get_fulfilment_breakdown(
    period: str = "monthly", service: WarehouseReportsService = Depends(get_warehouse_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_fulfilment_breakdown(user.entity_id, period))


@router.get("/top-requested-skus", response_model=ApiResponse[list[list]])
def get_top_requested_skus(
    period: str = "monthly", limit: int = 5,
    service: WarehouseReportsService = Depends(get_warehouse_reports_service), user: User = Depends(_portal),
):
    return ApiResponse(data=service.get_top_requested_skus(user.entity_id, period, limit))


@router.get("/vendor-po-status", response_model=ApiResponse[list[dict]])
def get_vendor_po_status(
    period: str = "monthly", service: WarehouseReportsService = Depends(get_warehouse_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_vendor_po_status(user.entity_id, period))
