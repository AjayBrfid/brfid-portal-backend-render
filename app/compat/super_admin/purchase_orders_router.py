"""vms-sa-react's cross-vendor Purchase Orders view (`/purchase-orders`) — genuinely new.
`itemsSummary` is always "1 line item": this codebase's PurchaseOrder models a single SKU-variant
line per order (no separate PO-line-items table), unlike the old contract's sample ("4 line
items"), which assumed a multi-line PO document — a genuine schema gap, not a bug. Status is
translated through _common.po_status_out (splits the real single "Delivered" terminal state into
the old contract's "Partially Delivered"/"Completed" using received_qty vs. quantity)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin._common import po_status_out, resolve_vendor_id, resolve_warehouse_id
from app.compat.super_admin.schemas import PurchaseOrderOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.procurement import PurchaseOrder
from app.models.user import User
from app.models.vendor import Vendor
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/purchase-orders", tags=["super-admin-compat-purchase-orders"])
_portal = require_portal("super_admin")


def _reshape(session: Session, rows: list[PurchaseOrder]) -> list[dict]:
    vendor_ids = {r.vendor_id for r in rows}
    warehouse_ids = {r.warehouse_id for r in rows}
    vendors = {v.id: v for v in session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars()} if vendor_ids else {}
    warehouses = {w.id: w for w in session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids))).scalars()} if warehouse_ids else {}

    items = []
    for r in rows:
        vendor = vendors.get(r.vendor_id)
        warehouse = warehouses.get(r.warehouse_id)
        items.append({
            "id": r.ref_code, "vendor_id": vendor.code if vendor else None, "vendor_name": vendor.name if vendor else None,
            "warehouse_id": warehouse.code if warehouse else None, "warehouse_name": warehouse.name if warehouse else None,
            "quotation_id": r.quotation_id, "items_summary": "1 line item", "grand_total": float(r.grand_total),
            "order_date": r.order_date, "delivery_date": r.delivery_date,
            "status": po_status_out(r.status, r.received_qty, r.quantity),
        })
    return items


@router.get("", response_model=ApiResponse[list[PurchaseOrderOut]])
def list_purchase_orders(
    search: str | None = None, status: str | None = None, vendorId: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(PurchaseOrder)
    if vendorId:
        stmt = stmt.where(PurchaseOrder.vendor_id == resolve_vendor_id(session, vendorId))
    if warehouseId:
        stmt = stmt.where(PurchaseOrder.warehouse_id == resolve_warehouse_id(session, warehouseId))
    stmt = stmt.order_by(PurchaseOrder.created_at.desc())
    rows, total = paginate(session, stmt, params)
    items = _reshape(session, rows)
    if status:
        items = [i for i in items if i["status"] == status]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/{po_id}", response_model=ApiResponse[PurchaseOrderOut])
def get_purchase_order(po_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    po = session.execute(select(PurchaseOrder).where(PurchaseOrder.ref_code == po_id)).scalar_one_or_none()
    if not po:
        raise NotFoundException("Purchase order not found")
    return ApiResponse(data=_reshape(session, [po])[0])
