import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.exceptions import NotFoundException
from app.models.retail import Store, StoreDiscount, StoreInventory, StoreProductSettings
from app.repositories.retail_repository import RetailRepository
from app.utils.pagination import PaginationParams


class ProductService:
    def __init__(self, session):
        self.session = session
        self.repo = RetailRepository(session)

    def _stock_status(self, stock: int, min_threshold: int) -> str:
        if stock <= 0:
            return "Out"
        if stock <= min_threshold:
            return "Low"
        return "In Stock"

    def _get_or_create_settings(self, store_id: uuid.UUID, sku_variant_id: uuid.UUID) -> StoreProductSettings:
        row = self.repo.get_settings(store_id, sku_variant_id)
        if not row:
            row = self.repo.add_settings(StoreProductSettings(store_id=store_id, sku_variant_id=sku_variant_id, visible=True))
        return row

    def _first_supplier_name(self, sku_variant_id: uuid.UUID) -> str | None:
        from app.repositories.catalog_repository import CatalogRepository

        vendor_id = CatalogRepository(self.session).first_supplying_vendor_id(sku_variant_id)
        if not vendor_id:
            return None
        from app.models.vendor import Vendor  # Phase 4

        vendor = self.session.get(Vendor, vendor_id)
        return vendor.name if vendor else None

    def _product_row(self, store: Store, inv: StoreInventory, variant, sku, settings: StoreProductSettings | None, discount: StoreDiscount | None) -> dict:
        min_threshold = inv.reorder_level if inv.reorder_level is not None else store.low_stock_threshold
        mrp = float(sku.mrp) if sku.mrp else 0
        price = mrp * (1 - float(discount.pct) / 100) if discount else mrp
        return {
            "sku": variant.variant_code, "name": sku.name, "cat": sku.category, "stock": inv.quantity,
            "min": min_threshold, "price": round(price, 2), "supplier": self._first_supplier_name(variant.id),
            "visible": settings.visible if settings else True, "mrp": mrp,
            "stock_status": self._stock_status(inv.quantity, min_threshold),
        }

    def list_products(self, store_id: uuid.UUID, params: PaginationParams, category: str | None, q: str | None, visible_only: bool):
        store = self.repo.get_by_id(store_id)
        rows = self.repo.inventory_for_store(store_id)
        if category:
            rows = [r for r in rows if r[2].category == category]
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in r[1].variant_code.lower() or ql in r[2].name.lower()]

        total = len(rows)
        page_rows = rows[params.offset : params.offset + params.limit]
        variant_ids = [v.id for _, v, _ in page_rows]
        settings_map = {s.sku_variant_id: s for s in (
            self.session.scalars(select(StoreProductSettings).where(StoreProductSettings.store_id == store_id, StoreProductSettings.sku_variant_id.in_(variant_ids))).all() if variant_ids else []
        )}
        discount_map = {d.sku_variant_id: d for d in (
            self.session.scalars(select(StoreDiscount).where(StoreDiscount.store_id == store_id, StoreDiscount.sku_variant_id.in_(variant_ids))).all() if variant_ids else []
        )}

        items = []
        for inv, variant, sku in page_rows:
            settings = settings_map.get(variant.id)
            if visible_only and settings and not settings.visible:
                continue
            items.append(self._product_row(store, inv, variant, sku, settings, discount_map.get(variant.id)))
        return items, total

    def get_product(self, store_id: uuid.UUID, sku_code: str) -> dict:
        store = self.repo.get_by_id(store_id)
        from app.models.catalog import Sku, SkuVariant

        row = self.session.execute(
            select(StoreInventory, SkuVariant, Sku)
            .join(SkuVariant, SkuVariant.id == StoreInventory.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(StoreInventory.store_id == store_id, SkuVariant.variant_code == sku_code)
        ).first()
        if not row:
            raise NotFoundException("Product not found")
        inv, variant, sku = row
        settings = self.repo.get_settings(store_id, variant.id)
        discount = self.repo.get_discount(store_id, variant.id)
        return self._product_row(store, inv, variant, sku, settings, discount)

    def list_categories(self, store_id: uuid.UUID) -> list[str]:
        from app.models.catalog import Sku, SkuVariant

        rows = self.session.execute(
            select(func.distinct(Sku.category))
            .join(SkuVariant, SkuVariant.sku_id == Sku.id)
            .join(StoreInventory, StoreInventory.sku_variant_id == SkuVariant.id)
            .where(StoreInventory.store_id == store_id, Sku.category.is_not(None))
        ).all()
        return [r[0] for r in rows]

    def update_visibility(self, store_id: uuid.UUID, updates: list[tuple[str, bool]], actor_user_id: uuid.UUID) -> int:
        from app.repositories.catalog_repository import CatalogRepository

        catalog = CatalogRepository(self.session)
        count = 0
        for sku_code, visible in updates:
            variant = catalog.get_variant_by_code(sku_code)
            if not variant:
                continue
            settings = self._get_or_create_settings(store_id, variant.id)
            settings.visible = visible
            if not visible:
                settings.removed_at = datetime.now(timezone.utc)
                settings.removed_by = actor_user_id
            count += 1
        self.session.commit()
        if count:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(actor_user_id, "store", "Product Visibility Updated", f"Updated visibility for {count} SKU(s).", "store", store_id)
        return count

    def list_removed(self, store_id: uuid.UUID) -> list[dict]:
        from app.models.catalog import Sku, SkuVariant
        from app.models.user import User

        rows = self.repo.removed_settings(store_id)
        items = []
        for row in rows:
            variant = self.session.get(SkuVariant, row.sku_variant_id)
            sku = self.session.get(Sku, variant.sku_id) if variant else None
            remover = self.session.get(User, row.removed_by) if row.removed_by else None
            items.append({"sku": variant.variant_code if variant else None, "name": sku.name if sku else None, "removed_at": row.removed_at, "removed_by": remover.name if remover else None})
        return items

    def restore_product(self, store_id: uuid.UUID, sku_code: str) -> dict:
        from app.repositories.catalog_repository import CatalogRepository

        variant = CatalogRepository(self.session).get_variant_by_code(sku_code)
        if not variant:
            raise NotFoundException("Product not found")
        settings = self._get_or_create_settings(store_id, variant.id)
        settings.visible = True
        settings.removed_at = None
        settings.removed_by = None
        self.session.commit()
        return {"sku": sku_code, "visible": True}

    def get_stock_summary(self, store_id: uuid.UUID) -> dict:
        store = self.repo.get_by_id(store_id)
        rows = self.repo.inventory_for_store(store_id)
        total_units = sum(inv.quantity for inv, _, _ in rows)
        total_products = len(rows)
        low_count = sum(1 for inv, _, _ in rows if 0 < inv.quantity <= (inv.reorder_level if inv.reorder_level is not None else store.low_stock_threshold))
        out_count = sum(1 for inv, _, _ in rows if inv.quantity <= 0)
        by_category: dict[str, int] = {}
        for inv, _, sku in rows:
            if sku.category:
                by_category[sku.category] = by_category.get(sku.category, 0) + inv.quantity
        capacity = 5000  # store capacity isn't a modeled column anywhere — a reasonable static default
        return {
            "total_units": total_units, "total_products": total_products, "low_stock_count": low_count,
            "out_of_stock_count": out_count, "store_capacity": capacity,
            "capacity_used_pct": round(total_units / capacity * 100) if capacity else 0,
            "by_category": [{"cat": cat, "units": units, "share_pct": round(units / total_units * 100) if total_units else 0} for cat, units in by_category.items()],
        }

    def list_stock_rows(self, store_id: uuid.UUID, only: str) -> list[dict]:
        """only: 'low' | 'out'"""
        store = self.repo.get_by_id(store_id)
        rows = self.repo.inventory_for_store(store_id)
        items = []
        for inv, variant, sku in rows:
            min_threshold = inv.reorder_level if inv.reorder_level is not None else store.low_stock_threshold
            status = self._stock_status(inv.quantity, min_threshold)
            if (only == "low" and status != "Low") or (only == "out" and status != "Out"):
                continue
            items.append({"sku": variant.variant_code, "name": sku.name, "cat": sku.category, "stock": inv.quantity, "min": min_threshold, "status": status})
        return items

    def get_low_stock_threshold(self, store_id: uuid.UUID) -> int:
        return self.repo.get_by_id(store_id).low_stock_threshold

    def set_low_stock_threshold(self, store_id: uuid.UUID, threshold: int) -> None:
        store = self.repo.get_by_id(store_id)
        store.low_stock_threshold = threshold
        self.session.commit()

    def list_discounts(self, store_id: uuid.UUID) -> list[dict]:
        from app.models.catalog import Sku, SkuVariant

        rows = self.repo.discounts_for_store(store_id)
        items = []
        for d in rows:
            variant = self.session.get(SkuVariant, d.sku_variant_id)
            sku = self.session.get(Sku, variant.sku_id) if variant else None
            mrp = float(sku.mrp) if sku and sku.mrp else 0
            items.append({"sku": variant.variant_code if variant else None, "name": sku.name if sku else None, "mrp": mrp, "pct": float(d.pct), "retail_price": round(mrp * (1 - float(d.pct) / 100), 2)})
        return items

    def apply_discount(self, store_id: uuid.UUID, sku_code: str, pct: float) -> dict:
        from app.models.catalog import Sku
        from app.repositories.catalog_repository import CatalogRepository

        variant = CatalogRepository(self.session).get_variant_by_code(sku_code)
        if not variant:
            raise NotFoundException("Product not found")
        row = self.repo.get_discount(store_id, variant.id)
        if not row:
            self.repo.add_discount(StoreDiscount(store_id=store_id, sku_variant_id=variant.id, pct=pct))
        else:
            row.pct = pct
        self.session.commit()
        sku = self.session.get(Sku, variant.sku_id)
        mrp = float(sku.mrp) if sku and sku.mrp else 0
        return {"sku": sku_code, "name": sku.name if sku else None, "mrp": mrp, "pct": pct, "retail_price": round(mrp * (1 - pct / 100), 2)}

    def delete_discount(self, store_id: uuid.UUID, sku_code: str) -> None:
        from app.repositories.catalog_repository import CatalogRepository

        variant = CatalogRepository(self.session).get_variant_by_code(sku_code)
        if not variant:
            raise NotFoundException("Product not found")
        row = self.repo.get_discount(store_id, variant.id)
        if row:
            self.repo.delete_discount(row)
            self.session.commit()
