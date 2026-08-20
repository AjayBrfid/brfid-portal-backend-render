"""vms-sa-react's cross-warehouse RFQs view (`/rfqs`) — genuinely new. `title`/`category` are
derived from the RFQ's linked Sku (Rfq itself has no title/category columns of its own — it's
raised against a specific sku_variant_id); `vendorsInvited`/`quotationsReceived` are simple
counts. Status is translated through _common.rfq_status_out — see that module's docstring for
why it's a lossy many-to-one mapping (the real RFQ state machine has 8 states, the old contract
only 5)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin._common import resolve_warehouse_id, rfq_status_out
from app.compat.super_admin.schemas import RfqOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.catalog import Sku, SkuVariant
from app.models.procurement import Quotation, Rfq, RfqInvitedVendor
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/rfqs", tags=["super-admin-compat-rfqs"])
_portal = require_portal("super_admin")


def _reshape(session: Session, rows: list[Rfq]) -> list[dict]:
    warehouse_ids = {r.warehouse_id for r in rows}
    warehouses = {w.id: w for w in session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids))).scalars()} if warehouse_ids else {}
    variant_ids = {r.sku_variant_id for r in rows}
    variant_rows = session.execute(
        select(SkuVariant, Sku).join(Sku, Sku.id == SkuVariant.sku_id).where(SkuVariant.id.in_(variant_ids))
    ).all() if variant_ids else []
    skus_by_variant = {v.id: sku for v, sku in variant_rows}

    rfq_ids = [r.id for r in rows]
    invited_counts = dict(session.execute(
        select(RfqInvitedVendor.rfq_id, func.count()).where(RfqInvitedVendor.rfq_id.in_(rfq_ids)).group_by(RfqInvitedVendor.rfq_id)
    ).all()) if rfq_ids else {}
    quote_counts = dict(session.execute(
        select(Quotation.rfq_id, func.count()).where(Quotation.rfq_id.in_(rfq_ids)).group_by(Quotation.rfq_id)
    ).all()) if rfq_ids else {}

    items = []
    for r in rows:
        warehouse = warehouses.get(r.warehouse_id)
        sku = skus_by_variant.get(r.sku_variant_id)
        items.append({
            "id": r.ref_code, "title": sku.name if sku else None, "category": sku.category if sku else None,
            "issue_date": r.issue_date, "closing_date": r.closing_date, "quantity": r.quantity,
            "unit": r.unit or (sku.unit if sku else "Pcs"), "status": rfq_status_out(r.status),
            "vendors_invited": invited_counts.get(r.id, 0), "quotations_received": quote_counts.get(r.id, 0),
            "warehouse_id": warehouse.code if warehouse else None, "warehouse_name": warehouse.name if warehouse else None,
        })
    return items


@router.get("", response_model=ApiResponse[list[RfqOut]])
def list_rfqs(
    search: str | None = None, status: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(Rfq)
    if warehouseId:
        stmt = stmt.where(Rfq.warehouse_id == resolve_warehouse_id(session, warehouseId))
    stmt = stmt.order_by(Rfq.created_at.desc())
    rows, total = paginate(session, stmt, params)
    items = _reshape(session, rows)
    if status:
        items = [i for i in items if i["status"] == status]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/{rfq_id}", response_model=ApiResponse[RfqOut])
def get_rfq(rfq_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    rfq = session.execute(select(Rfq).where(Rfq.ref_code == rfq_id)).scalar_one_or_none()
    if not rfq:
        raise NotFoundException("RFQ not found")
    return ApiResponse(data=_reshape(session, [rfq])[0])
