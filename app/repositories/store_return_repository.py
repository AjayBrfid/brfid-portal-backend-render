import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.retail import StoreReturn
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class StoreReturnRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, StoreReturn.ref_code, "RT")

    def add(self, row: StoreReturn) -> StoreReturn:
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, return_id: uuid.UUID) -> StoreReturn | None:
        return self.session.get(StoreReturn, return_id)

    def get_for_warehouse(self, warehouse_id: uuid.UUID, ref: str) -> StoreReturn | None:
        stmt = select(StoreReturn).where(StoreReturn.ref_code == ref, StoreReturn.warehouse_id == warehouse_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, decision: str | None, status: str | None):
        stmt = select(StoreReturn).where(StoreReturn.warehouse_id == warehouse_id)
        if decision:
            stmt = stmt.where(StoreReturn.decision == decision)
        if status:
            stmt = stmt.where(StoreReturn.status == status)
        if search:
            stmt = stmt.where(StoreReturn.ref_code.ilike(f"%{search}%"))
        stmt = stmt.order_by(StoreReturn.requested_at.desc())
        return paginate(self.session, stmt, params)

    def get_for_store(self, store_id: uuid.UUID, ref: str) -> StoreReturn | None:
        stmt = select(StoreReturn).where(StoreReturn.ref_code == ref, StoreReturn.store_id == store_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_store(self, store_id: uuid.UUID, params: PaginationParams, search: str | None):
        stmt = select(StoreReturn).where(StoreReturn.store_id == store_id)
        if search:
            stmt = stmt.where(StoreReturn.ref_code.ilike(f"%{search}%"))
        stmt = stmt.order_by(StoreReturn.requested_at.desc())
        return paginate(self.session, stmt, params)
