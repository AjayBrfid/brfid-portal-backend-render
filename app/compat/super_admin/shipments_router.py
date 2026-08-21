"""vms-sa-react's Inbound/Outbound Deliveries views, unified into a single Shipments view: one
list mixes the Shipment ledger (vendor -> warehouse, "Inbound") with the TransferOrder ledger
(warehouse -> store, "Outbound"), tagged with `direction` so the UI can tell them apart. Pure
reads, no new business logic — see _common.py's status-mapping docstrings for the handful of
vocabulary gaps between the old contract's statuses and this codebase's real enums.

Both source tables are fetched and paginated in Python rather than via a SQL UNION: they don't
share a column shape (Shipment has no store/request reference, TransferOrder has no expected-
delivery date), and every caller of this endpoint already requests the full collection in one
page (see frontend/super_admin/src/lib/apiResource.js) so there's no real-world page it would
need to fetch efficiently.
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin._common import (
    resolve_id,
    resolve_po_id,
    resolve_store_id,
    resolve_vendor_id,
    resolve_warehouse_id,
    shipment_status_out,
    transfer_status_out,
    transfer_statuses_for,
)
from app.compat.super_admin.schemas import ShipmentOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.fulfillment import PurchaseRequest, TransferOrder
from app.models.procurement import PurchaseOrder
from app.models.retail import Store
from app.models.shipping import Asn, Shipment
from app.models.user import User
from app.models.vendor import Vendor
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse, PaginationParams

router = APIRouter(prefix="/shipments", tags=["super-admin-compat-shipments"])
_portal = require_portal("super_admin")


def _inbound_reshape(session: Session, rows: list[Shipment]) -> list[dict]:
    asn_ids = {r.asn_id for r in rows}
    asns = {a.id: a for a in session.execute(select(Asn).where(Asn.id.in_(asn_ids))).scalars()} if asn_ids else {}
    po_ids = {a.po_id for a in asns.values()}
    pos = {p.id: p for p in session.execute(select(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids))).scalars()} if po_ids else {}
    vendor_ids = {p.vendor_id for p in pos.values()}
    warehouse_ids = {p.warehouse_id for p in pos.values()}
    vendors = {v.id: v for v in session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars()} if vendor_ids else {}
    warehouses = {w.id: w for w in session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids))).scalars()} if warehouse_ids else {}

    items = []
    for r in rows:
        asn = asns.get(r.asn_id)
        po = pos.get(asn.po_id) if asn else None
        vendor = vendors.get(po.vendor_id) if po else None
        warehouse = warehouses.get(po.warehouse_id) if po else None
        disp_status, delayed = shipment_status_out(r.status)
        items.append({
            "id": r.code or str(r.id), "direction": "Inbound", "po_id": po.ref_code if po else None,
            "request_id": None, "vendor_name": vendor.name if vendor else None, "store_name": None,
            "warehouse_name": warehouse.name if warehouse else None, "dispatch_date": r.dispatch_date,
            "expected_delivery": r.expected_delivery, "status": disp_status, "delayed": delayed,
            "tracking_no": r.tracking_no,
        })
    return items


def _list_inbound(
    session: Session, search: str | None, status: str | None, warehouse_id, po_id, vendor_id,
) -> list[dict]:
    needs_po_join = bool(vendor_id or warehouse_id)
    stmt = select(Shipment)
    asn_ids_stmt = select(Asn.id)
    if needs_po_join:
        asn_ids_stmt = asn_ids_stmt.join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
    if po_id:
        asn_ids_stmt = asn_ids_stmt.where(Asn.po_id == po_id)
    if vendor_id:
        asn_ids_stmt = asn_ids_stmt.where(PurchaseOrder.vendor_id == vendor_id)
    if warehouse_id:
        asn_ids_stmt = asn_ids_stmt.where(PurchaseOrder.warehouse_id == warehouse_id)
    if po_id or vendor_id or warehouse_id:
        stmt = stmt.where(Shipment.asn_id.in_(asn_ids_stmt))
    if search:
        stmt = stmt.where(Shipment.tracking_no.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(Shipment.status == status)
    rows = session.execute(stmt).scalars().all()
    return _inbound_reshape(session, rows)


_OUTBOUND_STATUS_TEMPLATE = {"Packed": 0, "Dispatched": 0, "In Transit": 0, "Delivered": 0, "Delayed": 0}


def _outbound_reshape(session: Session, rows: list[TransferOrder]) -> list[dict]:
    pr_ids = {r.pr_id for r in rows if r.pr_id}
    prs = {p.id: p for p in session.execute(select(PurchaseRequest).where(PurchaseRequest.id.in_(pr_ids))).scalars()} if pr_ids else {}
    store_ids = {r.store_id for r in rows}
    warehouse_ids = {r.warehouse_id for r in rows}
    stores = {s.id: s for s in session.execute(select(Store).where(Store.id.in_(store_ids))).scalars()} if store_ids else {}
    warehouses = {w.id: w for w in session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids))).scalars()} if warehouse_ids else {}

    items = []
    for r in rows:
        pr = prs.get(r.pr_id) if r.pr_id else None
        store = stores.get(r.store_id)
        warehouse = warehouses.get(r.warehouse_id)
        items.append({
            "id": r.ref_code, "direction": "Outbound", "po_id": None,
            "request_id": pr.ref_code if pr else None, "vendor_name": None,
            "store_name": store.name if store else None, "warehouse_name": warehouse.name if warehouse else None,
            "dispatch_date": r.dispatched_at.date() if r.dispatched_at else None,
            "expected_delivery": None,  # not tracked on TransferOrder — see schemas.py docstring
            "status": transfer_status_out(r.status), "delayed": False, "tracking_no": r.tracking_number,
        })
    return items


def _list_outbound(
    session: Session, search: str | None, status: str | None, warehouse_id, request_id, store_id,
) -> list[dict]:
    stmt = select(TransferOrder)
    if request_id:
        stmt = stmt.where(TransferOrder.pr_id == request_id)
    if store_id:
        stmt = stmt.where(TransferOrder.store_id == store_id)
    if warehouse_id:
        stmt = stmt.where(TransferOrder.warehouse_id == warehouse_id)
    if search:
        stmt = stmt.where(TransferOrder.ref_code.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(TransferOrder.status.in_(transfer_statuses_for(status)))
    rows = session.execute(stmt).scalars().all()
    return _outbound_reshape(session, rows)


@router.get("", response_model=ApiResponse[list[ShipmentOut]])
def list_shipments(
    search: str | None = None, status: str | None = None, direction: str | None = None,
    poId: str | None = None, requestId: str | None = None, vendorId: str | None = None,
    storeId: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    warehouse_id = resolve_warehouse_id(session, warehouseId) if warehouseId else None

    items: list[dict] = []
    if direction != "Outbound":
        po_id = resolve_po_id(session, poId) if poId else None
        vendor_id = resolve_vendor_id(session, vendorId) if vendorId else None
        items.extend(_list_inbound(session, search, status, warehouse_id, po_id, vendor_id))
    if direction != "Inbound":
        store_id = resolve_store_id(session, storeId) if storeId else None
        pr_id = resolve_id(session, PurchaseRequest, PurchaseRequest.ref_code, requestId) if requestId else None
        items.extend(_list_outbound(session, search, status, warehouse_id, pr_id, store_id))

    items.sort(key=lambda r: r["dispatch_date"] or date.min, reverse=True)

    total_items = len(items)
    page = items[params.offset: params.offset + params.limit]
    return ApiResponse(data=page, meta=admin_meta(params.page, params.limit, total_items))


@router.get("/stats", response_model=ApiResponse[dict])
def shipment_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    result = dict(_OUTBOUND_STATUS_TEMPLATE)

    inbound_rows = session.execute(select(Shipment.status, func.count()).group_by(Shipment.status)).all()
    for real_status, count in inbound_rows:
        disp_status, delayed = shipment_status_out(real_status)
        key = "Delayed" if delayed else disp_status
        result[key] = result.get(key, 0) + count

    outbound_rows = session.execute(select(TransferOrder.status, func.count()).group_by(TransferOrder.status)).all()
    for real_status, count in outbound_rows:
        key = transfer_status_out(real_status)
        result[key] = result.get(key, 0) + count

    return ApiResponse(data=result)


@router.get("/{shipment_id}", response_model=ApiResponse[ShipmentOut])
def get_shipment(shipment_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    shipment = session.execute(select(Shipment).where(Shipment.code == shipment_id)).scalar_one_or_none()
    if shipment:
        return ApiResponse(data=_inbound_reshape(session, [shipment])[0])

    transfer = session.execute(select(TransferOrder).where(TransferOrder.ref_code == shipment_id)).scalar_one_or_none()
    if transfer:
        return ApiResponse(data=_outbound_reshape(session, [transfer])[0])

    raise NotFoundException("Shipment not found")
