import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuStatus, SkuSupplyingVendor, SkuVariant, WarehouseSkuStatus


class CatalogRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_active_variants(self, search: str | None, category: str | None, gender: str | None, colour: str | None):
        """Every active-SKU variant, joined with its style — the master product catalogue
        surfaced to warehouse/retail once Super Admin has approved it (generate_sku sets
        Sku.status ACTIVE), independent of whether any physical stock has arrived yet."""
        stmt = (
            select(SkuVariant, Sku)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(Sku.status == SkuStatus.ACTIVE)
        )
        if search:
            like = f"%{search}%"
            stmt = stmt.where((SkuVariant.variant_code.ilike(like)) | (Sku.name.ilike(like)))
        if category:
            stmt = stmt.where(Sku.category == category)
        if gender:
            stmt = stmt.where(Sku.gender == gender)
        if colour:
            stmt = stmt.where(SkuVariant.colour == colour)
        stmt = stmt.order_by(Sku.published_at.desc())
        return self.session.execute(stmt).all()

    def distinct_categories(self) -> list[str]:
        stmt = select(Sku.category).where(Sku.status == SkuStatus.ACTIVE, Sku.category.is_not(None)).distinct()
        return sorted(self.session.execute(stmt).scalars().all())

    def distinct_genders(self) -> list[str]:
        stmt = select(Sku.gender).where(Sku.status == SkuStatus.ACTIVE, Sku.gender.is_not(None)).distinct()
        return sorted(self.session.execute(stmt).scalars().all())

    def supplying_vendor_ids_map(self, sku_variant_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
        if not sku_variant_ids:
            return {}
        rows = self.session.execute(
            select(SkuSupplyingVendor.sku_variant_id, SkuSupplyingVendor.vendor_id).where(
                SkuSupplyingVendor.sku_variant_id.in_(sku_variant_ids)
            )
        ).all()
        out: dict[uuid.UUID, list[uuid.UUID]] = {}
        for variant_id, vendor_id in rows:
            out.setdefault(variant_id, []).append(vendor_id)
        return out

    def find_matching_variant(self, category: str, gender: str, fabric: str, gsm: str, colour: str, size: str):
        """An active Sku+SkuVariant whose full specification already matches — used at SKU
        generation time so two catalog submissions for the same product (regardless of their
        own free-text names) become one SKU with multiple supplying vendors, not duplicates."""
        stmt = (
            select(SkuVariant, Sku)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(
                Sku.status == SkuStatus.ACTIVE,
                Sku.category == category,
                Sku.gender == gender,
                Sku.fabric == fabric,
                Sku.gsm == gsm,
                SkuVariant.colour == colour,
                SkuVariant.size == size,
            )
        )
        return self.session.execute(stmt).first()

    def distinct_supplying_vendor_ids(self) -> list[uuid.UUID]:
        stmt = (
            select(SkuSupplyingVendor.vendor_id)
            .join(SkuVariant, SkuVariant.id == SkuSupplyingVendor.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(Sku.status == SkuStatus.ACTIVE)
            .distinct()
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_sku_by_style_code(self, style_code: str) -> Sku | None:
        return self.session.execute(select(Sku).where(Sku.style_code == style_code)).scalar_one_or_none()

    def get_variant_by_code(self, variant_code: str) -> SkuVariant | None:
        return self.session.execute(select(SkuVariant).where(SkuVariant.variant_code == variant_code)).scalar_one_or_none()

    def variants_for_sku(self, sku_id: uuid.UUID) -> list[SkuVariant]:
        return list(self.session.scalars(select(SkuVariant).where(SkuVariant.sku_id == sku_id)).all())

    def get_variant(self, variant_id: uuid.UUID) -> SkuVariant | None:
        return self.session.get(SkuVariant, variant_id)

    def get_sku(self, sku_id: uuid.UUID) -> Sku | None:
        return self.session.get(Sku, sku_id)

    def supplying_vendor_ids(self, sku_variant_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(SkuSupplyingVendor.vendor_id).where(SkuSupplyingVendor.sku_variant_id == sku_variant_id)
        return list(self.session.execute(stmt).scalars().all())

    def first_supplying_vendor_id(self, sku_variant_id: uuid.UUID) -> uuid.UUID | None:
        stmt = select(SkuSupplyingVendor.vendor_id).where(SkuSupplyingVendor.sku_variant_id == sku_variant_id)
        return self.session.execute(stmt).scalars().first()

    def get_warehouse_sku_status(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID) -> WarehouseSkuStatus | None:
        return self.session.get(WarehouseSkuStatus, (warehouse_id, sku_variant_id))

    def add_warehouse_sku_status(self, row: WarehouseSkuStatus) -> WarehouseSkuStatus:
        self.session.add(row)
        self.session.flush()
        return row
