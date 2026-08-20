"""vms-sa-react's Products supporting-entity view (`/products`) — genuinely new. Reads the
master Sku catalog directly. Note: the old contract's sample ids look like a short "PRD-001"
business code, but this schema never modeled one for Sku (only `style_code`, a *style* code, not
a per-product display code) — `id` here is the real Sku UUID primary key instead, consistent
with how /store-inventory and /vendor-stock resolve `productId` elsewhere in this compat layer."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import ProductOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.catalog import Sku
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/products", tags=["super-admin-compat-products"])
_portal = require_portal("super_admin")


def _to_out(sku: Sku) -> dict:
    return {
        "id": sku.id, "sku": f"SKU-{sku.style_code}", "name": sku.name, "category": sku.category, "unit": sku.unit,
        "reorder_level": sku.reorder_level, "unit_price": float(sku.mrp) if sku.mrp is not None else None,
    }


@router.get("", response_model=ApiResponse[list[ProductOut]])
def list_products(
    search: str | None = None, status: str | None = None, params: PaginationParams = Depends(),
    session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(Sku)
    if search:
        stmt = stmt.where(Sku.name.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(Sku.status == status)
    stmt = stmt.order_by(Sku.published_at.desc())
    rows, total = paginate(session, stmt, params)
    return ApiResponse(data=[_to_out(s) for s in rows], meta=admin_meta(params.page, params.limit, total))


@router.get("/{product_id}", response_model=ApiResponse[ProductOut])
def get_product(product_id: str, session: Session = Depends(get_db), _: User = Depends(_portal)):
    sku = session.get(Sku, product_id)
    if not sku:
        raise NotFoundException("Product not found")
    return ApiResponse(data=_to_out(sku))
