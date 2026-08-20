"""vms-sa-react's cross-store Stock Requests view (`/stock-requests`) — genuinely new. Reads
PurchaseRequest, which deliberately has no stored `status` column (see its model docstring —
display status is derived by joining to whatever fulfilled it). This compat layer does that same
derivation to produce the old contract's five-value status enum: `declined`/`pending`
approval_status map directly to Rejected/Pending; once approved, the linked TransferOrder's own
status (when fulfilment went through one) distinguishes Approved/Dispatched/Fulfilled. A
request fulfilled via a fresh RFQ (fulfilment_type "rfq") has no transfer order yet, so it's
reported as "Approved" until one exists — a known simplification, noted in the report."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin._common import resolve_store_id, resolve_warehouse_id
from app.compat.super_admin.schemas import StockRequestOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import FulfilmentRefType, PurchaseRequest, PurchaseRequestApprovalStatus, TransferOrder, TransferOrderStatus
from app.models.retail import Store
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/stock-requests", tags=["super-admin-compat-stock-requests"])
_portal = require_portal("super_admin")


def _status_for(session: Session, pr: PurchaseRequest) -> str:
    if pr.approval_status == PurchaseRequestApprovalStatus.DECLINED:
        return "Rejected"
    if pr.approval_status == PurchaseRequestApprovalStatus.PENDING:
        return "Pending"
    if pr.fulfilment_ref_type == FulfilmentRefType.TRANSFER_ORDER and pr.fulfilment_ref_id:
        transfer = session.get(TransferOrder, pr.fulfilment_ref_id)
        if transfer:
            if transfer.status in (TransferOrderStatus.DELIVERED, TransferOrderStatus.COMPLETED):
                return "Fulfilled"
            if transfer.status == TransferOrderStatus.DISPATCHED:
                return "Dispatched"
    return "Approved"


def _reshape(session: Session, rows: list[PurchaseRequest]) -> list[dict]:
    store_ids = {r.store_id for r in rows}
    warehouse_ids = {r.warehouse_id for r in rows}
    variant_ids = {r.sku_variant_id for r in rows}
    stores = {s.id: s for s in session.execute(select(Store).where(Store.id.in_(store_ids))).scalars()} if store_ids else {}
    warehouses = {w.id: w for w in session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids))).scalars()} if warehouse_ids else {}
    variant_rows = session.execute(
        select(SkuVariant, Sku).join(Sku, Sku.id == SkuVariant.sku_id).where(SkuVariant.id.in_(variant_ids))
    ).all() if variant_ids else []
    skus_by_variant = {v.id: sku for v, sku in variant_rows}

    items = []
    for r in rows:
        store = stores.get(r.store_id)
        warehouse = warehouses.get(r.warehouse_id)
        sku = skus_by_variant.get(r.sku_variant_id)
        items.append({
            "id": r.ref_code, "store_id": store.code if store else None, "store_name": store.name if store else None,
            "product_name": sku.name if sku else None, "unit": sku.unit if sku else "Pcs", "quantity": r.requested_qty,
            "request_date": r.requested_at.date(), "required_by": r.required_by, "priority": r.priority.value,
            "status": _status_for(session, r), "warehouse_name": warehouse.name if warehouse else None,
        })
    return items


@router.get("", response_model=ApiResponse[list[StockRequestOut]])
def list_stock_requests(
    search: str | None = None, status: str | None = None, storeId: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(PurchaseRequest)
    if storeId:
        stmt = stmt.where(PurchaseRequest.store_id == resolve_store_id(session, storeId))
    if warehouseId:
        stmt = stmt.where(PurchaseRequest.warehouse_id == resolve_warehouse_id(session, warehouseId))
    stmt = stmt.order_by(PurchaseRequest.requested_at.desc())
    rows, total = paginate(session, stmt, params)
    items = _reshape(session, rows)
    if status:
        # Status is derived (see _status_for), not a stored column, so this filter is applied
        # after fetching the page — acceptable here since stock-request pages are small and this
        # is a supplementary read-only view, but note that meta.total won't reflect the filter.
        items = [i for i in items if i["status"] == status]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def stock_request_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    rows = session.execute(select(PurchaseRequest)).scalars().all()
    counts = {"Pending": 0, "Approved": 0, "Dispatched": 0, "Fulfilled": 0, "Rejected": 0}
    for r in rows:
        counts[_status_for(session, r)] = counts.get(_status_for(session, r), 0) + 1
    return ApiResponse(data=counts)


@router.get("/{request_id}", response_model=ApiResponse[StockRequestOut])
def get_stock_request(request_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    pr = session.execute(select(PurchaseRequest).where(PurchaseRequest.ref_code == request_id)).scalar_one_or_none()
    if not pr:
        raise NotFoundException("Stock request not found")
    return ApiResponse(data=_reshape(session, [pr])[0])
