"""vms-sa-react's Inbound/Outbound Deliveries views — genuinely new super-admin-scoped read
endpoints (no such view existed anywhere in the unified backend yet). Inbound reads the existing
Shipment ledger (joined through Asn -> PurchaseOrder for vendor/warehouse names); outbound reads
the existing TransferOrder ledger (joined through PurchaseRequest/Store/Warehouse). Pure reads,
no new business logic — see _common.py's status-mapping docstrings for the handful of vocabulary
gaps between the old contract's statuses and this codebase's real enums."""
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
from app.compat.super_admin.schemas import InboundDeliveryOut, OutboundDeliveryOut
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
from app.utils.pagination import paginate

inbound_router = APIRouter(prefix="/inbound-deliveries", tags=["super-admin-compat-inbound-deliveries"])
outbound_router = APIRouter(prefix="/outbound-deliveries", tags=["super-admin-compat-outbound-deliveries"])
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
            "id": r.code or str(r.id), "po_id": po.ref_code if po else None, "vendor_name": vendor.name if vendor else None,
            "warehouse_name": warehouse.name if warehouse else None, "dispatch_date": r.dispatch_date,
            "expected_delivery": r.expected_delivery, "status": disp_status, "delayed": delayed,
            "tracking_no": r.tracking_no,
        })
    return items


@inbound_router.get("", response_model=ApiResponse[list[InboundDeliveryOut]])
def list_inbound_deliveries(
    search: str | None = None, status: str | None = None, poId: str | None = None,
    vendorId: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    asn_ids_stmt = select(Asn.id)
    needs_po_join = bool(vendorId or warehouseId)
    if needs_po_join:
        asn_ids_stmt = asn_ids_stmt.join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
    if poId:
        asn_ids_stmt = asn_ids_stmt.where(Asn.po_id == resolve_po_id(session, poId))
    if vendorId:
        asn_ids_stmt = asn_ids_stmt.where(PurchaseOrder.vendor_id == resolve_vendor_id(session, vendorId))
    if warehouseId:
        asn_ids_stmt = asn_ids_stmt.where(PurchaseOrder.warehouse_id == resolve_warehouse_id(session, warehouseId))

    stmt = select(Shipment)
    if poId or vendorId or warehouseId:
        stmt = stmt.where(Shipment.asn_id.in_(asn_ids_stmt))
    if search:
        stmt = stmt.where(Shipment.tracking_no.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(Shipment.status == status)
    stmt = stmt.order_by(Shipment.dispatch_date.desc())
    rows, total = paginate(session, stmt, params)
    return ApiResponse(data=_inbound_reshape(session, rows), meta=admin_meta(params.page, params.limit, total))


@inbound_router.get("/stats", response_model=ApiResponse[dict])
def inbound_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    rows = session.execute(select(Shipment.status, func.count()).group_by(Shipment.status)).all()
    return ApiResponse(data={status.value: count for status, count in rows})


@inbound_router.get("/{delivery_id}", response_model=ApiResponse[InboundDeliveryOut])
def get_inbound_delivery(delivery_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    shipment = session.execute(select(Shipment).where(Shipment.code == delivery_id)).scalar_one_or_none()
    if not shipment:
        raise NotFoundException("Inbound delivery not found")
    return ApiResponse(data=_inbound_reshape(session, [shipment])[0])


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
            "id": r.ref_code, "request_id": pr.ref_code if pr else None, "store_name": store.name if store else None,
            "warehouse_name": warehouse.name if warehouse else None,
            "dispatch_date": r.dispatched_at.date() if r.dispatched_at else None,
            "expected_delivery": None,  # not tracked on TransferOrder — see schemas.py docstring
            "status": transfer_status_out(r.status), "delayed": False, "tracking_no": r.tracking_number,
        })
    return items


@outbound_router.get("", response_model=ApiResponse[list[OutboundDeliveryOut]])
def list_outbound_deliveries(
    search: str | None = None, status: str | None = None, requestId: str | None = None,
    storeId: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(TransferOrder)
    if requestId:
        stmt = stmt.where(TransferOrder.pr_id == resolve_id(session, PurchaseRequest, PurchaseRequest.ref_code, requestId))
    if storeId:
        stmt = stmt.where(TransferOrder.store_id == resolve_store_id(session, storeId))
    if warehouseId:
        stmt = stmt.where(TransferOrder.warehouse_id == resolve_warehouse_id(session, warehouseId))
    if search:
        stmt = stmt.where(TransferOrder.ref_code.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(TransferOrder.status.in_(transfer_statuses_for(status)))
    stmt = stmt.order_by(TransferOrder.created_at.desc())
    rows, total = paginate(session, stmt, params)
    return ApiResponse(data=_outbound_reshape(session, rows), meta=admin_meta(params.page, params.limit, total))


@outbound_router.get("/stats", response_model=ApiResponse[dict])
def outbound_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    rows = session.execute(select(TransferOrder.status, func.count()).group_by(TransferOrder.status)).all()
    result = dict(_OUTBOUND_STATUS_TEMPLATE)
    for real_status, count in rows:
        result[transfer_status_out(real_status)] = result.get(transfer_status_out(real_status), 0) + count
    return ApiResponse(data=result)


@outbound_router.get("/{delivery_id}", response_model=ApiResponse[OutboundDeliveryOut])
def get_outbound_delivery(delivery_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    transfer = session.execute(select(TransferOrder).where(TransferOrder.ref_code == delivery_id)).scalar_one_or_none()
    if not transfer:
        raise NotFoundException("Outbound delivery not found")
    return ApiResponse(data=_outbound_reshape(session, [transfer])[0])
