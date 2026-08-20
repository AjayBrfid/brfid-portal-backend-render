"""Master product catalogue — the read-only view of every Super-Admin-approved SKU
(Sku.status ACTIVE, set by AdminVendorService.generate_sku), shared by the warehouse
"Product Catalogue" screen and the retail "Product Catalogue" screen. Neither requires a
physical stock row to exist first; that's the warehouse Inventory / retail Products screens'
job (backed by Inventory / StoreInventory), a separate concept from catalogue visibility.
"""
import uuid

from sqlalchemy import select

from app.models.vendor import Vendor
from app.repositories.catalog_repository import CatalogRepository
from app.utils.pagination import PaginationParams


class MasterCatalogService:
    def __init__(self, session):
        self.session = session
        self.repo = CatalogRepository(session)

    def _row(self, variant, sku, vendor_ids: list[uuid.UUID]) -> dict:
        return {
            "variant_code": variant.variant_code, "name": sku.name, "category": sku.category,
            "gender": sku.gender, "fabric": sku.fabric, "gsm": sku.gsm, "colour": variant.colour,
            "size": variant.size, "supplying_vendor_ids": vendor_ids,
        }

    def list_catalogue(self, params: PaginationParams, search: str | None, category: str | None, gender: str | None, colour: str | None):
        rows = self.repo.list_active_variants(search, category, gender, colour)
        total = len(rows)
        page_rows = rows[params.offset : params.offset + params.limit]
        vendor_map = self.repo.supplying_vendor_ids_map([variant.id for variant, _ in page_rows])
        items = [self._row(variant, sku, vendor_map.get(variant.id, [])) for variant, sku in page_rows]
        return items, total

    def list_types(self) -> list[str]:
        return self.repo.distinct_categories()

    def list_genders(self) -> list[str]:
        return self.repo.distinct_genders()

    def list_supplying_vendors(self) -> list[dict]:
        vendor_ids = self.repo.distinct_supplying_vendor_ids()
        if not vendor_ids:
            return []
        vendors = self.session.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids))).all()
        return [{"id": v.id, "name": v.name} for v in vendors]
