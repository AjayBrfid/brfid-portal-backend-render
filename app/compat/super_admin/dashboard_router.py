"""vms-sa-react's Dashboard Summary + Registration Trend (`/dashboard/summary`,
`/analytics/registrations`) — neither existed anywhere in the unified backend before (super
admin never had a dashboard/analytics view). Both are simple read-only counts/aggregations
directly against Vendor/Warehouse/Store, reusing this codebase's existing repo.count_by_status
convention for the summary and mirroring app/api/v1/vendor/dashboard_router.py's fixed-window
style for the trend (see _common.py's registration_buckets)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.super_admin._common import registration_buckets, window_start
from app.compat.super_admin.schemas import DashboardSummaryOut, RegistrationTrendOut
from app.core.exceptions import ValidationException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.super_admin import get_admin_store_service, get_admin_vendor_service, get_admin_warehouse_service
from app.models.retail import Store
from app.models.user import User
from app.models.vendor import Vendor
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse
from app.services.super_admin.store_admin_service import AdminStoreService
from app.services.super_admin.vendor_admin_service import AdminVendorService
from app.services.super_admin.warehouse_admin_service import AdminWarehouseService

router = APIRouter(tags=["super-admin-compat-dashboard"])
_portal = require_portal("super_admin")

_ENTITY_MODELS = {
    "vendors": (Vendor, Vendor.registered_on),
    "warehouses": (Warehouse, Warehouse.registered_on),
    "stores": (Store, Store.opened_on),
}


@router.get("/dashboard/summary", response_model=ApiResponse[DashboardSummaryOut])
def dashboard_summary(
    vendor_service: AdminVendorService = Depends(get_admin_vendor_service),
    warehouse_service: AdminWarehouseService = Depends(get_admin_warehouse_service),
    store_service: AdminStoreService = Depends(get_admin_store_service),
    _: User = Depends(_portal),
):
    # Reuses each domain's existing count_by_status() aggregation (the same one backing
    # /vendors/stats, /warehouses/stats, /stores/stats) rather than issuing fresh count queries.
    vendor_counts = vendor_service.stats()
    warehouse_counts = warehouse_service.stats()
    store_counts = store_service.stats()
    return ApiResponse(data={
        "total_vendors": sum(vendor_counts.values()), "total_warehouses": sum(warehouse_counts.values()),
        "total_stores": sum(store_counts.values()),
        "pending_vendors": vendor_counts.get("Pending Approval", 0),
        "pending_warehouses": warehouse_counts.get("Pending Approval", 0),
        "pending_stores": store_counts.get("Pending Approval", 0),
    })


@router.get("/analytics/registrations", response_model=ApiResponse[RegistrationTrendOut])
def registration_trend(
    entity: str = Query(...), period: str = Query("month"),
    session: Session = Depends(get_db), _: User = Depends(_portal),
):
    if entity not in _ENTITY_MODELS:
        raise ValidationException("entity must be one of: vendors, warehouses, stores")
    model, date_column = _ENTITY_MODELS[entity]
    rows = session.execute(select(date_column).where(date_column >= window_start(period))).scalars().all()
    dates = [d.date() if hasattr(d, "date") else d for d in rows]
    return ApiResponse(data={"entity": entity, "period": period, "buckets": registration_buckets(dates, period)})
