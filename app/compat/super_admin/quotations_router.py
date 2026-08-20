"""vms-sa-react's cross-vendor Quotations view (`/quotations`) — genuinely new (no
super-admin-scoped quotations view existed before). Reads the existing Quotation/Rfq tables
directly; QuotationStatus already matches the old contract's four values exactly, so no status
translation is needed here (unlike RFQs/POs/deliveries)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin._common import resolve_vendor_id, resolve_warehouse_id
from app.compat.super_admin.schemas import QuotationOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.catalog import Sku, SkuVariant
from app.models.procurement import Quotation, Rfq
from app.models.user import User
from app.models.vendor import Vendor
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/quotations", tags=["super-admin-compat-quotations"])
_portal = require_portal("super_admin")


def _reshape(session: Session, rows: list[Quotation]) -> list[dict]:
    rfq_ids = {q.rfq_id for q in rows}
    rfqs = {r.id: r for r in session.execute(select(Rfq).where(Rfq.id.in_(rfq_ids))).scalars()} if rfq_ids else {}
    vendor_ids = {q.vendor_id for q in rows}
    vendors = {v.id: v for v in session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars()} if vendor_ids else {}
    warehouse_ids = {r.warehouse_id for r in rfqs.values()}
    warehouses = {w.id: w for w in session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids))).scalars()} if warehouse_ids else {}
    variant_ids = {r.sku_variant_id for r in rfqs.values()}
    variant_rows = session.execute(
        select(SkuVariant, Sku).join(Sku, Sku.id == SkuVariant.sku_id).where(SkuVariant.id.in_(variant_ids))
    ).all() if variant_ids else []
    skus_by_variant = {v.id: sku for v, sku in variant_rows}

    items = []
    for q in rows:
        rfq = rfqs.get(q.rfq_id)
        vendor = vendors.get(q.vendor_id)
        warehouse = warehouses.get(rfq.warehouse_id) if rfq else None
        sku = skus_by_variant.get(rfq.sku_variant_id) if rfq else None
        # Quotation stores only the final tax/discount-inclusive total — the pre-tax "amount" the
        # old contract also wants is derived here (unit_price * RFQ quantity), not a stored field.
        amount = round(float(q.unit_price) * rfq.quantity, 2) if rfq else float(q.unit_price)
        items.append({
            "id": q.code or str(q.id), "rfq_id": rfq.ref_code if rfq else None, "rfq_title": sku.name if sku else None,
            "vendor_id": vendor.code if vendor else None, "vendor_name": vendor.name if vendor else None,
            "amount": amount, "total_amount": float(q.total_amount), "submitted_date": q.submitted_date.date(),
            "delivery_days": q.delivery_days, "status": q.status.value,
            "warehouse_id": warehouse.code if warehouse else None, "warehouse_name": warehouse.name if warehouse else None,
        })
    return items


@router.get("", response_model=ApiResponse[list[QuotationOut]])
def list_quotations(
    search: str | None = None, status: str | None = None, rfqId: str | None = None,
    vendorId: str | None = None, warehouseId: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(Quotation)
    if rfqId or warehouseId:
        stmt = stmt.join(Rfq, Rfq.id == Quotation.rfq_id)
        if rfqId:
            stmt = stmt.where(Rfq.ref_code == rfqId)
        if warehouseId:
            stmt = stmt.where(Rfq.warehouse_id == resolve_warehouse_id(session, warehouseId))
    if vendorId:
        stmt = stmt.where(Quotation.vendor_id == resolve_vendor_id(session, vendorId))
    if status:
        stmt = stmt.where(Quotation.status == status)
    stmt = stmt.order_by(Quotation.submitted_date.desc())
    rows, total = paginate(session, stmt, params)
    return ApiResponse(data=_reshape(session, rows), meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def quotation_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    rows = session.execute(select(Quotation.status, func.count()).group_by(Quotation.status)).all()
    return ApiResponse(data={status.value: count for status, count in rows})


@router.get("/{quotation_id}", response_model=ApiResponse[QuotationOut])
def get_quotation(quotation_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    quotation = session.execute(select(Quotation).where(Quotation.code == quotation_id)).scalar_one_or_none()
    if not quotation:
        raise NotFoundException("Quotation not found")
    return ApiResponse(data=_reshape(session, [quotation])[0])
