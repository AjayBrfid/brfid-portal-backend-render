import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.procurement import PurchaseOrder, Quotation, Rfq, RfqInvitedVendor
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class RfqRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, Rfq.ref_code, "RFQ")

    def add(self, rfq: Rfq) -> Rfq:
        self.session.add(rfq)
        self.session.flush()
        return rfq

    def get_by_id(self, rfq_id: uuid.UUID) -> Rfq | None:
        return self.session.get(Rfq, rfq_id)

    def get_for_warehouse(self, warehouse_id: uuid.UUID, rfq_id: uuid.UUID) -> Rfq | None:
        stmt = select(Rfq).where(Rfq.id == rfq_id, Rfq.warehouse_id == warehouse_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None = None, status: str | None = None):
        stmt = select(Rfq).where(Rfq.warehouse_id == warehouse_id)
        if search:
            stmt = stmt.where(Rfq.ref_code.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Rfq.status == status)
        stmt = stmt.order_by(Rfq.created_at.desc())
        return paginate(self.session, stmt, params)

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        stmt = (
            select(Rfq)
            .join(RfqInvitedVendor, RfqInvitedVendor.rfq_id == Rfq.id)
            .where(RfqInvitedVendor.vendor_id == vendor_id)
        )
        if status:
            stmt = stmt.where(Rfq.status == status)
        stmt = stmt.order_by(Rfq.created_at.desc())
        return paginate(self.session, stmt, params)

    def add_invited_vendor(self, row: RfqInvitedVendor) -> RfqInvitedVendor:
        self.session.add(row)
        self.session.flush()
        return row

    def invited_vendor_ids(self, rfq_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(RfqInvitedVendor.vendor_id).where(RfqInvitedVendor.rfq_id == rfq_id)
        return list(self.session.execute(stmt).scalars().all())

    def is_vendor_invited(self, rfq_id: uuid.UUID, vendor_id: uuid.UUID) -> bool:
        stmt = select(RfqInvitedVendor).where(RfqInvitedVendor.rfq_id == rfq_id, RfqInvitedVendor.vendor_id == vendor_id)
        return self.session.execute(stmt).scalar_one_or_none() is not None


class QuotationRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_code(self) -> str:
        return next_sequential_code(self.session, Quotation.code, "QT")

    def add(self, quotation: Quotation) -> Quotation:
        self.session.add(quotation)
        self.session.flush()
        return quotation

    def get_by_id(self, quotation_id: uuid.UUID) -> Quotation | None:
        return self.session.get(Quotation, quotation_id)

    def list_for_rfq(self, rfq_id: uuid.UUID) -> list[Quotation]:
        stmt = select(Quotation).where(Quotation.rfq_id == rfq_id).order_by(Quotation.submitted_date.desc())
        return list(self.session.scalars(stmt).all())

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        stmt = select(Quotation).where(Quotation.vendor_id == vendor_id).order_by(Quotation.submitted_date.desc())
        return paginate(self.session, stmt, params)

    def get_for_vendor(self, vendor_id: uuid.UUID, quotation_id: uuid.UUID) -> Quotation | None:
        stmt = select(Quotation).where(Quotation.id == quotation_id, Quotation.vendor_id == vendor_id)
        return self.session.execute(stmt).scalar_one_or_none()


class PurchaseOrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, PurchaseOrder.ref_code, "PO")

    def add(self, po: PurchaseOrder) -> PurchaseOrder:
        self.session.add(po)
        self.session.flush()
        return po

    def get_by_id(self, po_id: uuid.UUID) -> PurchaseOrder | None:
        return self.session.get(PurchaseOrder, po_id)

    def get_for_warehouse(self, warehouse_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder | None:
        stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.warehouse_id == warehouse_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_for_vendor(self, vendor_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder | None:
        stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.vendor_id == vendor_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None = None, status: str | None = None):
        stmt = select(PurchaseOrder).where(PurchaseOrder.warehouse_id == warehouse_id)
        if search:
            stmt = stmt.where(PurchaseOrder.ref_code.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
        stmt = stmt.order_by(PurchaseOrder.created_at.desc())
        return paginate(self.session, stmt, params)

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        stmt = select(PurchaseOrder).where(PurchaseOrder.vendor_id == vendor_id)
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
        stmt = stmt.order_by(PurchaseOrder.created_at.desc())
        return paginate(self.session, stmt, params)
