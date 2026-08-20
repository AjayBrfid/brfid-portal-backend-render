"""vms-sa-react's Store Inventory view (`/store-inventory`). The real
`/api/v1/super-admin/store-inventory` route requires `storeId`; the old contract treats it as
optional, so this is a fresh (but simple) read directly against StoreInventory joined to
SkuVariant/Sku/Store when no store is specified — no store/warehouse/vendor business logic
involved, just a wider SELECT."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import StoreInventoryOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.catalog import Sku, SkuVariant
from app.models.retail import Store, StoreInventory
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams
from app.utils.pagination import paginate

router = APIRouter(prefix="/store-inventory", tags=["super-admin-compat-store-inventory"])
_portal = require_portal("super_admin")


def _status_for(quantity: int, reorder_level: int | None) -> str:
    if quantity <= 0:
        return "Out of Stock"
    if reorder_level is not None and quantity <= reorder_level:
        return "Low Stock"
    return "In Stock"


@router.get("", response_model=ApiResponse[list[StoreInventoryOut]])
def list_store_inventory(
    storeId: str | None = None, productId: str | None = None, params: PaginationParams = Depends(),
    session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(StoreInventory)
    store = None
    if storeId:
        store = session.execute(select(Store).where(Store.code == storeId)).scalar_one_or_none()
        if not store:
            raise NotFoundException(f"Store '{storeId}' not found")
        stmt = stmt.where(StoreInventory.store_id == store.id)
    if productId:
        stmt = stmt.join(SkuVariant, SkuVariant.id == StoreInventory.sku_variant_id).join(Sku, Sku.id == SkuVariant.sku_id).where(Sku.id == productId)
    rows, total = paginate(session, stmt, params)

    store_ids = {store.id} if store else {r.store_id for r in rows}
    stores = {s.id: s for s in session.execute(select(Store).where(Store.id.in_(store_ids))).scalars()} if store_ids else {}
    variant_ids = {r.sku_variant_id for r in rows}
    variant_rows = session.execute(
        select(SkuVariant, Sku).join(Sku, Sku.id == SkuVariant.sku_id).where(SkuVariant.id.in_(variant_ids))
    ).all() if variant_ids else []
    variants = {v.id: (v, sku) for v, sku in variant_rows}

    items = []
    for r in rows:
        s = stores.get(r.store_id)
        variant, sku = variants.get(r.sku_variant_id, (None, None))
        items.append({
            "store_id": s.code if s else None, "store_name": s.name if s else None,
            "product_id": sku.id if sku else None, "product_name": sku.name if sku else None,
            "unit": sku.unit if sku else "Pcs", "quantity": r.quantity, "reorder_level": r.reorder_level,
            "status": _status_for(r.quantity, r.reorder_level), "last_updated": r.updated_at.date(),
        })
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))
