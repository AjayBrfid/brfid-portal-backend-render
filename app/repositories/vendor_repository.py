import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.vendor import Vendor, VendorCatalogSubmission, VendorGood
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


_VENDOR_SORT_COLUMNS = {
    "name": Vendor.name,
    "code": Vendor.code,
    "status": Vendor.status,
    "rating": Vendor.rating,
    "registered_on": Vendor.registered_on,
    "created_at": Vendor.created_at,
}


class VendorRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, vendor_id: uuid.UUID) -> Vendor | None:
        return self.session.get(Vendor, vendor_id)

    def get_by_code(self, code: str) -> Vendor | None:
        return self.session.execute(select(Vendor).where(Vendor.code == code)).scalar_one_or_none()

    def get_by_gst(self, gst: str) -> Vendor | None:
        return self.session.execute(select(Vendor).where(Vendor.gst == gst)).scalar_one_or_none()

    def get_by_pan(self, pan: str) -> Vendor | None:
        return self.session.execute(select(Vendor).where(Vendor.pan == pan)).scalar_one_or_none()

    def next_code(self) -> str:
        return next_sequential_code(self.session, Vendor.code, "VEN-")

    def next_good_code(self) -> str:
        return next_sequential_code(self.session, VendorGood.code, "GD")

    def next_catalog_code(self) -> str:
        return next_sequential_code(self.session, VendorCatalogSubmission.code, "CAT")

    def add(self, vendor: Vendor) -> Vendor:
        self.session.add(vendor)
        self.session.flush()
        return vendor

    def list_all(
        self, params: PaginationParams, search: str | None = None, status: str | None = None,
        sort: str | None = None, order: str | None = None,
    ):
        stmt = select(Vendor)
        if search:
            stmt = stmt.where(Vendor.name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Vendor.status == status)
        sort_column = _VENDOR_SORT_COLUMNS.get(sort, Vendor.registered_on)
        stmt = stmt.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
        return paginate(self.session, stmt, params)

    def count_by_status(self) -> dict:
        rows = self.session.execute(select(Vendor.status, func.count()).group_by(Vendor.status)).all()
        return {status.value: count for status, count in rows}

    def goods_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        stmt = select(VendorGood).where(VendorGood.vendor_id == vendor_id).order_by(VendorGood.created_at.desc())
        return paginate(self.session, stmt, params)

    def get_good(self, good_id: uuid.UUID) -> VendorGood | None:
        return self.session.get(VendorGood, good_id)

    def add_good(self, good: VendorGood) -> VendorGood:
        self.session.add(good)
        self.session.flush()
        return good

    def catalog_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        stmt = select(VendorCatalogSubmission).where(VendorCatalogSubmission.vendor_id == vendor_id).order_by(VendorCatalogSubmission.submitted_date.desc())
        return paginate(self.session, stmt, params)

    def list_all_catalog(self, params: PaginationParams, search: str | None = None, status: str | None = None):
        stmt = select(VendorCatalogSubmission)
        if search:
            stmt = stmt.where(VendorCatalogSubmission.name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(VendorCatalogSubmission.status == status)
        stmt = stmt.order_by(VendorCatalogSubmission.submitted_date.desc())
        return paginate(self.session, stmt, params)

    def get_catalog_submission(self, submission_id: uuid.UUID) -> VendorCatalogSubmission | None:
        return self.session.get(VendorCatalogSubmission, submission_id)

    def add_catalog_submission(self, row: VendorCatalogSubmission) -> VendorCatalogSubmission:
        self.session.add(row)
        self.session.flush()
        return row
