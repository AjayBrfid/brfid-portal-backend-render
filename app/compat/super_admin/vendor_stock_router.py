"""vms-sa-react's cross-vendor Vendor Stock view (`/vendor-stock...`). VendorGood is a vendor's
own raw-material/component catalog — it has no link to a specific finished product or
warehouse, so `productId`/`warehouseId` are accepted as query params (per the old spec) but are
genuinely no-ops here; see VendorStockOut's docstring-equivalent comments in schemas.py."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import VendorStockOut
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.user import User
from app.models.vendor import Vendor, VendorGood
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/vendor-stock", tags=["super-admin-compat-vendor-stock"])
_portal = require_portal("super_admin")


@router.get("", response_model=ApiResponse[list[VendorStockOut]])
def list_vendor_stock(
    search: str | None = None, status: str | None = None, vendorId: str | None = None,
    warehouseId: str | None = None, productId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(VendorGood)
    if search:
        stmt = stmt.where(VendorGood.name.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(VendorGood.stock_status == status)
    if vendorId:
        vendor = session.execute(select(Vendor).where(Vendor.code == vendorId)).scalar_one_or_none()
        stmt = stmt.where(VendorGood.vendor_id == (vendor.id if vendor else None))
    stmt = stmt.order_by(VendorGood.created_at.desc())
    rows, total = paginate(session, stmt, params)

    vendor_ids = {g.vendor_id for g in rows}
    vendors = {v.id: v for v in session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars()} if vendor_ids else {}
    items = [
        {
            "id": g.id, "vendor_id": vendors[g.vendor_id].code if g.vendor_id in vendors else None,
            "vendor_name": vendors[g.vendor_id].name if g.vendor_id in vendors else None,
            "product_name": g.name, "unit": g.unit.value, "quantity": float(g.quantity),
            "last_updated": g.created_at.date(), "status": g.stock_status.value,
        }
        for g in rows
    ]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def vendor_stock_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    rows = session.execute(select(VendorGood.stock_status, func.count()).group_by(VendorGood.stock_status)).all()
    return ApiResponse(data={status.value: count for status, count in rows})
