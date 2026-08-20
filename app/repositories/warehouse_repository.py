import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseStockMovement, WarehouseStoreLink, WarehouseVendorLink, WarehouseZone
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class WarehouseRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, warehouse_id: uuid.UUID) -> Warehouse | None:
        return self.session.get(Warehouse, warehouse_id)

    def get_by_code(self, code: str) -> Warehouse | None:
        return self.session.execute(select(Warehouse).where(Warehouse.code == code)).scalar_one_or_none()

    def next_code(self) -> str:
        return next_sequential_code(self.session, Warehouse.code, "WH")

    def add(self, warehouse: Warehouse) -> Warehouse:
        self.session.add(warehouse)
        self.session.flush()
        return warehouse

    def list_all(self, params: PaginationParams, search: str | None = None, status: str | None = None):
        stmt = select(Warehouse)
        if search:
            stmt = stmt.where(Warehouse.name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Warehouse.status == status)
        stmt = stmt.order_by(Warehouse.registered_on.desc())
        return paginate(self.session, stmt, params)

    def count_by_status(self) -> dict:
        rows = self.session.execute(select(Warehouse.status, func.count()).group_by(Warehouse.status)).all()
        return {status.value: count for status, count in rows}

    def list_active_ids(self) -> list[uuid.UUID]:
        stmt = select(Warehouse.id).where(Warehouse.status == WarehouseStatus.ACTIVE)
        return list(self.session.execute(stmt).scalars().all())

    # --- vendor roster ---

    def get_vendor_link(self, warehouse_id: uuid.UUID, vendor_id: uuid.UUID) -> WarehouseVendorLink | None:
        stmt = select(WarehouseVendorLink).where(
            WarehouseVendorLink.warehouse_id == warehouse_id, WarehouseVendorLink.vendor_id == vendor_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def active_vendor_links(self, warehouse_id: uuid.UUID) -> list[WarehouseVendorLink]:
        stmt = select(WarehouseVendorLink).where(
            WarehouseVendorLink.warehouse_id == warehouse_id, WarehouseVendorLink.unlinked_at.is_(None)
        )
        return list(self.session.execute(stmt).scalars().all())

    def add_vendor_link(self, link: WarehouseVendorLink) -> WarehouseVendorLink:
        self.session.add(link)
        self.session.flush()
        return link

    # --- store roster ---

    def get_store_link(self, warehouse_id: uuid.UUID, store_id: uuid.UUID) -> WarehouseStoreLink | None:
        stmt = select(WarehouseStoreLink).where(
            WarehouseStoreLink.warehouse_id == warehouse_id, WarehouseStoreLink.store_id == store_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def active_store_links(self, warehouse_id: uuid.UUID) -> list[WarehouseStoreLink]:
        stmt = select(WarehouseStoreLink).where(
            WarehouseStoreLink.warehouse_id == warehouse_id, WarehouseStoreLink.unlinked_at.is_(None)
        )
        return list(self.session.execute(stmt).scalars().all())

    def add_store_link(self, link: WarehouseStoreLink) -> WarehouseStoreLink:
        self.session.add(link)
        self.session.flush()
        return link

    def linked_warehouses_for_store(self, store_id: uuid.UUID) -> list[Warehouse]:
        stmt = (
            select(Warehouse)
            .join(WarehouseStoreLink, WarehouseStoreLink.warehouse_id == Warehouse.id)
            .where(WarehouseStoreLink.store_id == store_id, WarehouseStoreLink.unlinked_at.is_(None))
        )
        return list(self.session.execute(stmt).scalars().all())

    # --- zones / stock movements (super admin) ---

    def zones_for_warehouse(self, warehouse_id: uuid.UUID) -> list[WarehouseZone]:
        return list(self.session.scalars(select(WarehouseZone).where(WarehouseZone.warehouse_id == warehouse_id)).all())

    def get_zone(self, zone_id: uuid.UUID) -> WarehouseZone | None:
        return self.session.get(WarehouseZone, zone_id)

    def movements_for_warehouse(self, warehouse_id: uuid.UUID, search: str | None, params: PaginationParams):
        stmt = select(WarehouseStockMovement).where(WarehouseStockMovement.warehouse_id == warehouse_id)
        if search:
            stmt = stmt.where(WarehouseStockMovement.product_name.ilike(f"%{search}%"))
        stmt = stmt.order_by(WarehouseStockMovement.occurred_at.desc())
        return paginate(self.session, stmt, params)

    def manager_name(self, warehouse_id: uuid.UUID) -> str | None:
        # manager_id is never actually assigned anywhere (no "add a warehouse manager" flow
        # exists), so it always looked up nothing. The one real person on file for a warehouse
        # is whoever registered it (the wh-admin user), so that's who shows as "Manager" now.
        from app.models.user import User

        admin_user = self.session.execute(
            select(User).where(User.entity_id == warehouse_id, User.portal_type == "warehouse")
        ).scalars().first()
        return admin_user.name if admin_user else None
