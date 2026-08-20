import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vendor_return import VendorReturn, VendorReturnAttachment
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class VendorReturnRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, VendorReturn.ref_code, "VR")

    def add(self, row: VendorReturn) -> VendorReturn:
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, return_id: uuid.UUID) -> VendorReturn | None:
        return self.session.get(VendorReturn, return_id)

    def get_for_vendor(self, vendor_id: uuid.UUID, return_id: uuid.UUID) -> VendorReturn | None:
        stmt = select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.vendor_id == vendor_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_for_warehouse(self, warehouse_id: uuid.UUID, return_id: uuid.UUID) -> VendorReturn | None:
        stmt = select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.warehouse_id == warehouse_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        stmt = select(VendorReturn).where(VendorReturn.vendor_id == vendor_id)
        if status:
            stmt = stmt.where(VendorReturn.status == status)
        stmt = stmt.order_by(VendorReturn.created_at.desc())
        return paginate(self.session, stmt, params)

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        stmt = select(VendorReturn).where(VendorReturn.warehouse_id == warehouse_id)
        if status:
            stmt = stmt.where(VendorReturn.status == status)
        stmt = stmt.order_by(VendorReturn.created_at.desc())
        return paginate(self.session, stmt, params)

    def add_attachment(self, attachment: VendorReturnAttachment) -> VendorReturnAttachment:
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def attachments_for_return(self, return_id: uuid.UUID) -> list[VendorReturnAttachment]:
        stmt = select(VendorReturnAttachment).where(VendorReturnAttachment.vendor_return_id == return_id)
        return list(self.session.scalars(stmt).all())

    def get_attachment(self, return_id: uuid.UUID, attachment_id: uuid.UUID) -> VendorReturnAttachment | None:
        stmt = select(VendorReturnAttachment).where(
            VendorReturnAttachment.id == attachment_id, VendorReturnAttachment.vendor_return_id == return_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()
