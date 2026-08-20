"""Dashboard compat -- thin camelCase wrapper over the exact same real
app/api/v1/vendor/dashboard_router.py functions (get_kpis/get_revenue_graph), which already
compute every figure from the same repositories. No duplicated aggregation logic here.
"""
from datetime import date

from fastapi import APIRouter, Depends

from app.api.v1.vendor.dashboard_router import export_report as _export_report
from app.api.v1.vendor.dashboard_router import get_kpis as _get_kpis
from app.api.v1.vendor.dashboard_router import get_revenue_graph as _get_revenue_graph
from app.compat.vendor.common import camelize, envelope
from app.dependencies.database import get_db
from app.dependencies.vendor import get_current_vendor
from app.models.vendor import Vendor

router = APIRouter(prefix="/dashboard", tags=["vendor-compat-dashboard"])


@router.get("/kpis")
def get_kpis(period: str = "month", vendor: Vendor = Depends(get_current_vendor), session=Depends(get_db)):
    result = _get_kpis(period=period, vendor=vendor, session=session)
    return envelope(camelize(result.data))


@router.get("/graphs/revenue")
def get_revenue_graph(period: str = "month", vendor: Vendor = Depends(get_current_vendor), session=Depends(get_db)):
    result = _get_revenue_graph(period=period, vendor=vendor, session=session)
    return envelope(camelize(result.data))


@router.get("/export-report")
def export_report(
    mode: str, date: date, vendor: Vendor = Depends(get_current_vendor), session=Depends(get_db),
):
    return _export_report(mode=mode, date=date, vendor=vendor, session=session)
