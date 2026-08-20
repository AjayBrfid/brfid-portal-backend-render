"""Goods (My Goods) compat. Confirmed against src/components/GoodsManager.jsx: the frontend
reads `code`/`id`, `stockStatus`, and `assignedSku` (resolved via any of this good's catalog
submissions that already has a sku_variant_id) -- everything else matches GoodsService's own
field names 1:1, just camelCased. Reuses the exact same category/unit picklist mapping already
defined in auth_router.py for vendor registration's own goods step.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.compat.schemas import CamelModel
from app.compat.vendor.auth_router import _GOODS_CATEGORY_MAP, _GOODS_UNIT_MAP
from app.compat.vendor.common import envelope, paginate_list, vendor_meta
from app.dependencies.vendor import get_current_vendor, get_goods_service
from app.models.catalog import SkuVariant
from app.models.vendor import Vendor, VendorCatalogSubmission
from app.schemas.common import PaginationParams
from app.services.vendor.goods_service import GoodsService

router = APIRouter(prefix="/goods", tags=["vendor-compat-goods"])

_ALL = PaginationParams(page=1, limit=100000)


def _assigned_sku(session, vendor_id, good_id) -> str | None:
    submission = session.execute(
        select(VendorCatalogSubmission).where(
            VendorCatalogSubmission.goods_id == good_id,
            VendorCatalogSubmission.vendor_id == vendor_id,
            VendorCatalogSubmission.sku_variant_id.is_not(None),
        )
    ).scalars().first()
    if not submission:
        return None
    variant = session.get(SkuVariant, submission.sku_variant_id)
    return variant.variant_code if variant else None


def _goods_out(session, vendor_id, good: dict) -> dict:
    return {
        "id": str(good["id"]),
        "code": good["code"],
        "name": good["name"],
        "category": good["category"],
        "unit": good["unit"],
        "quantity": good["quantity"],
        "price": good["price"],
        "stockStatus": good["stock_status"],
        "assignedSku": _assigned_sku(session, vendor_id, good["id"]),
    }


class GoodsCreateRequest(CamelModel):
    name: str
    category: str
    unit: str
    quantity: float
    price: float


class GoodsUpdateRequest(CamelModel):
    name: str | None = None
    category: str | None = None
    unit: str | None = None
    quantity: float | None = None
    price: float | None = None


@router.get("")
def list_goods(
    page: int = 1, limit: int = 20, search: str | None = None, category: str | None = None,
    service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor),
):
    rows, _ = service.list_for_vendor(vendor.id, _ALL)
    items = [_goods_out(service.session, vendor.id, g) for g in rows]
    if category:
        items = [i for i in items if i["category"] == category]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["name"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.post("", status_code=201)
def create_goods(body: GoodsCreateRequest, service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    category = _GOODS_CATEGORY_MAP.get(body.category, body.category)
    unit = _GOODS_UNIT_MAP.get(body.unit, body.unit)
    good = service.create(vendor.id, body.name, category, unit, body.quantity, body.price, None)
    return envelope(_goods_out(service.session, vendor.id, good))


@router.patch("/{good_id}")
def update_goods(good_id: str, body: GoodsUpdateRequest, service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    fields = body.model_dump(exclude_unset=True)
    if "category" in fields:
        fields["category"] = _GOODS_CATEGORY_MAP.get(fields["category"], fields["category"])
    if "unit" in fields:
        fields["unit"] = _GOODS_UNIT_MAP.get(fields["unit"], fields["unit"])
    good = service.update(vendor.id, good_id, **fields)
    return envelope(_goods_out(service.session, vendor.id, good))


@router.delete("/{good_id}")
def delete_goods(good_id: str, service: GoodsService = Depends(get_goods_service), vendor: Vendor = Depends(get_current_vendor)):
    service.delete(vendor.id, good_id)
    return envelope({"message": "Goods item deleted"})
