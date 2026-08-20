import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fulfillment import Inventory, InventoryReservation, PurchaseRequest, TransferOrder
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class InventoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID) -> Inventory | None:
        return self.session.get(Inventory, (warehouse_id, sku_variant_id))

    def add(self, row: Inventory) -> Inventory:
        self.session.add(row)
        self.session.flush()
        return row

    def joined_for_warehouse(self, warehouse_id: uuid.UUID, search: str | None, category: str | None):
        from app.models.catalog import Sku, SkuVariant

        stmt = (
            select(Inventory, SkuVariant, Sku)
            .join(SkuVariant, SkuVariant.id == Inventory.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(Inventory.warehouse_id == warehouse_id)
        )
        if search:
            stmt = stmt.where(SkuVariant.variant_code.ilike(f"%{search}%") | Sku.name.ilike(f"%{search}%"))
        if category:
            stmt = stmt.where(Sku.category == category)
        return self.session.execute(stmt).all()

    def joined_for_variant_code(self, warehouse_id: uuid.UUID, variant_code: str):
        from app.models.catalog import Sku, SkuVariant

        stmt = (
            select(Inventory, SkuVariant, Sku)
            .join(SkuVariant, SkuVariant.id == Inventory.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(Inventory.warehouse_id == warehouse_id, SkuVariant.variant_code == variant_code)
        )
        return self.session.execute(stmt).first()

    def for_variant_ids(self, warehouse_id: uuid.UUID, variant_ids: list[uuid.UUID]) -> list[Inventory]:
        if not variant_ids:
            return []
        stmt = select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.sku_variant_id.in_(variant_ids))
        return list(self.session.scalars(stmt).all())

    def reserved_by_variant(self, warehouse_id: uuid.UUID, variant_ids: list[uuid.UUID]) -> dict:
        if not variant_ids:
            return {}
        rows = self.session.execute(
            select(InventoryReservation.sku_variant_id, func.sum(InventoryReservation.reserved_qty))
            .where(InventoryReservation.warehouse_id == warehouse_id, InventoryReservation.sku_variant_id.in_(variant_ids))
            .group_by(InventoryReservation.sku_variant_id)
        ).all()
        return {variant_id: int(total) for variant_id, total in rows}

    def joined_reservations(self, warehouse_id: uuid.UUID, params: PaginationParams):
        from app.models.catalog import SkuVariant
        from app.models.retail import Store

        stmt = (
            select(InventoryReservation, PurchaseRequest, Store, SkuVariant)
            .join(PurchaseRequest, PurchaseRequest.id == InventoryReservation.pr_id)
            .join(Store, Store.id == PurchaseRequest.store_id)
            .join(SkuVariant, SkuVariant.id == InventoryReservation.sku_variant_id)
            .where(InventoryReservation.warehouse_id == warehouse_id)
            .order_by(InventoryReservation.reserved_at.desc())
        )
        all_rows = self.session.execute(stmt).all()
        total = len(all_rows)
        rows = all_rows[params.offset : params.offset + params.limit]
        return rows, total



class PurchaseRequestRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, PurchaseRequest.ref_code, "PR")

    def add(self, pr: PurchaseRequest) -> PurchaseRequest:
        self.session.add(pr)
        self.session.flush()
        return pr

    def get_by_id(self, pr_id: uuid.UUID) -> PurchaseRequest | None:
        return self.session.get(PurchaseRequest, pr_id)

    def get_by_ref(self, warehouse_id: uuid.UUID, ref: str) -> PurchaseRequest | None:
        stmt = select(PurchaseRequest).where(PurchaseRequest.ref_code == ref, PurchaseRequest.warehouse_id == warehouse_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_warehouse(
        self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, date_from: date | None, date_to: date | None
    ):
        stmt = select(PurchaseRequest).where(PurchaseRequest.warehouse_id == warehouse_id)
        if search:
            stmt = stmt.where(PurchaseRequest.ref_code.ilike(f"%{search}%"))
        if date_from:
            stmt = stmt.where(PurchaseRequest.requested_at >= date_from)
        if date_to:
            stmt = stmt.where(PurchaseRequest.requested_at <= date_to)
        stmt = stmt.order_by(PurchaseRequest.requested_at.desc())
        return paginate(self.session, stmt, params)

    def list_for_store(self, store_id: uuid.UUID, params: PaginationParams, search: str | None):
        stmt = select(PurchaseRequest).where(PurchaseRequest.store_id == store_id)
        if search:
            stmt = stmt.where(PurchaseRequest.ref_code.ilike(f"%{search}%"))
        stmt = stmt.order_by(PurchaseRequest.requested_at.desc())
        return paginate(self.session, stmt, params)


class TransferOrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, TransferOrder.ref_code, "TO")

    def add(self, to: TransferOrder) -> TransferOrder:
        self.session.add(to)
        self.session.flush()
        return to

    def get_for_warehouse(self, warehouse_id: uuid.UUID, to_id: uuid.UUID) -> TransferOrder | None:
        stmt = select(TransferOrder).where(TransferOrder.id == to_id, TransferOrder.warehouse_id == warehouse_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_warehouse(
        self,
        warehouse_id: uuid.UUID,
        params: PaginationParams,
        search: str | None,
        status: str | None,
        source_type: str | None,
        date_from: date | None,
        date_to: date | None,
    ):
        stmt = select(TransferOrder).where(TransferOrder.warehouse_id == warehouse_id)
        if status:
            stmt = stmt.where(TransferOrder.status == status)
        if source_type:
            stmt = stmt.where(TransferOrder.source_type == source_type)
        if search:
            stmt = stmt.where(TransferOrder.ref_code.ilike(f"%{search}%"))
        if date_from:
            stmt = stmt.where(TransferOrder.created_at >= date_from)
        if date_to:
            stmt = stmt.where(TransferOrder.created_at <= date_to)
        stmt = stmt.order_by(TransferOrder.created_at.desc())
        return paginate(self.session, stmt, params)
