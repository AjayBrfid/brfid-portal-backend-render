import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.retail import Store, StoreApproval, StoreDiscount, StoreInventory, StoreProductSettings, StoreStatus
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class RetailRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, store_id: uuid.UUID) -> Store | None:
        return self.session.get(Store, store_id)

    def get_by_code(self, code: str) -> Store | None:
        return self.session.execute(select(Store).where(Store.code == code)).scalar_one_or_none()

    def next_code(self) -> str:
        return next_sequential_code(self.session, Store.code, "STR-")

    def add(self, store: Store) -> Store:
        self.session.add(store)
        self.session.flush()
        return store

    def list_all(self, params: PaginationParams, search: str | None = None, status: str | None = None):
        stmt = select(Store)
        if search:
            stmt = stmt.where(Store.name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Store.status == status)
        stmt = stmt.order_by(Store.opened_on.desc())
        return paginate(self.session, stmt, params)

    def count_by_status(self) -> dict:
        rows = self.session.execute(select(Store.status, func.count()).group_by(Store.status)).all()
        return {status.value: count for status, count in rows}

    def list_active_ids(self) -> list[uuid.UUID]:
        stmt = select(Store.id).where(Store.status == StoreStatus.ACTIVE)
        return list(self.session.execute(stmt).scalars().all())

    # --- approvals ---

    def get_approval(self, approval_id: uuid.UUID) -> StoreApproval | None:
        return self.session.get(StoreApproval, approval_id)

    def add_approval(self, approval: StoreApproval) -> StoreApproval:
        self.session.add(approval)
        self.session.flush()
        return approval

    # --- per-store product/stock/discount ---

    def inventory_for_store(self, store_id: uuid.UUID):
        from app.models.catalog import Sku, SkuVariant

        stmt = (
            select(StoreInventory, SkuVariant, Sku)
            .join(SkuVariant, SkuVariant.id == StoreInventory.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(StoreInventory.store_id == store_id)
        )
        return self.session.execute(stmt).all()

    def get_settings(self, store_id: uuid.UUID, sku_variant_id: uuid.UUID) -> StoreProductSettings | None:
        return self.session.get(StoreProductSettings, (store_id, sku_variant_id))

    def add_settings(self, row: StoreProductSettings) -> StoreProductSettings:
        self.session.add(row)
        self.session.flush()
        return row

    def removed_settings(self, store_id: uuid.UUID) -> list[StoreProductSettings]:
        stmt = select(StoreProductSettings).where(
            StoreProductSettings.store_id == store_id, StoreProductSettings.visible.is_(False)
        )
        return list(self.session.scalars(stmt).all())

    def get_discount(self, store_id: uuid.UUID, sku_variant_id: uuid.UUID) -> StoreDiscount | None:
        return self.session.get(StoreDiscount, (store_id, sku_variant_id))

    def discounts_for_store(self, store_id: uuid.UUID) -> list[StoreDiscount]:
        return list(self.session.scalars(select(StoreDiscount).where(StoreDiscount.store_id == store_id)).all())

    def add_discount(self, row: StoreDiscount) -> StoreDiscount:
        self.session.add(row)
        self.session.flush()
        return row

    def delete_discount(self, row: StoreDiscount) -> None:
        self.session.delete(row)
