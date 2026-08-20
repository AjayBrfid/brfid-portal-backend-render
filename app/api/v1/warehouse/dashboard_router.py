from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.warehouse import get_warehouse_dashboard_service
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse
from app.services.reports.warehouse_report_service import build_warehouse_report_sections
from app.services.warehouse.dashboard_service import WarehouseDashboardService
from app.utils.date_range import resolve_week_or_month_range
from app.utils.excel_export import build_business_report_workbook

router = APIRouter(prefix="/dashboard", tags=["warehouse-dashboard"])
_portal = require_portal("warehouse")


@router.get("/summary", response_model=ApiResponse[dict])
def get_summary(service: WarehouseDashboardService = Depends(get_warehouse_dashboard_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_summary(user.entity_id))


@router.get("/goods-flow", response_model=ApiResponse[dict])
def get_goods_flow(
    period: str = "monthly", service: WarehouseDashboardService = Depends(get_warehouse_dashboard_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_goods_flow(user.entity_id, period))


@router.get("/top-skus", response_model=ApiResponse[list[dict]])
def get_top_skus(
    period: str = "monthly", limit: int = 5,
    service: WarehouseDashboardService = Depends(get_warehouse_dashboard_service), user: User = Depends(_portal),
):
    return ApiResponse(data=service.get_top_skus(user.entity_id, period, limit))


@router.get("/export-report")
def export_report(
    mode: str, date: date, user: User = Depends(_portal), session=Depends(get_db),
):
    warehouse = session.get(Warehouse, user.entity_id)
    start, end, period_label = resolve_week_or_month_range(mode, date)
    sections = build_warehouse_report_sections(session, user.entity_id, start, end)
    details = {
        "Warehouse Code": warehouse.code, "Name": warehouse.name, "Company Name": warehouse.company_name,
        "GSTIN": warehouse.gstin, "Address": warehouse.address, "City": warehouse.city, "State": warehouse.state,
        "Phone": warehouse.contact_phone, "Email": warehouse.contact_email,
    }
    buffer = build_business_report_workbook("Warehouse", details, period_label, sections)
    filename = f"warehouse_report_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
