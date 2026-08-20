from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.retail import get_retail_dashboard_service
from app.models.retail import Store
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.reports.retail_report_service import build_retail_report_sections
from app.services.retail.dashboard_service import RetailDashboardService
from app.utils.date_range import resolve_week_or_month_range
from app.utils.excel_export import build_business_report_workbook

router = APIRouter(prefix="/dashboard", tags=["retail-dashboard"])
_portal = require_portal("store")


@router.get("/manager", response_model=ApiResponse[dict])
def get_manager_dashboard(
    sales_period: str = "weekly", top_sell_period: str = "weekly",
    service: RetailDashboardService = Depends(get_retail_dashboard_service), user: User = Depends(_portal),
):
    return ApiResponse(data=service.get_manager_dashboard(user.entity_id, user.id, sales_period, top_sell_period))


@router.get("/admin", response_model=ApiResponse[dict])
def get_admin_dashboard(
    sales_period: str = "weekly", top_sell_period: str = "weekly",
    service: RetailDashboardService = Depends(get_retail_dashboard_service), user: User = Depends(_portal),
):
    return ApiResponse(data=service.get_admin_dashboard(user.entity_id, user.id, sales_period, top_sell_period))


@router.get("/export-report")
def export_report(
    mode: str, date: date, user: User = Depends(_portal), session=Depends(get_db),
):
    store = session.get(Store, user.entity_id)
    start, end, period_label = resolve_week_or_month_range(mode, date)
    sections = build_retail_report_sections(session, user.entity_id, start, end)
    details = {
        "Store Code": store.code, "Name": store.name, "Address": store.address, "City": store.city,
        "State": store.state, "GSTIN": store.gstin, "Phone": store.contact_phone,
    }
    buffer = build_business_report_workbook("Retail", details, period_label, sections)
    filename = f"retail_report_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
