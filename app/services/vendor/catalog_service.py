import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.vendor import CatalogSubmissionStatus, VendorCatalogDocument, VendorCatalogSubmission
from app.repositories.vendor_repository import VendorRepository
from app.utils.pagination import PaginationParams
from app.utils.storage import get_storage_client


class CatalogService:
    """A vendor's product-catalog submissions — reviewed by Super Admin, which turns an
    approved submission into a real SKU (see app/services/super_admin/vendor_admin_service.py::
    generate_sku)."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = VendorRepository(session)

    def to_out(self, row: VendorCatalogSubmission) -> dict:
        return {
            "id": row.id, "code": row.code, "name": row.name, "product_type": row.product_type, "gender": row.gender,
            "fabric": row.fabric, "colour": row.colour, "size": row.size, "gsm": row.gsm, "description": row.description,
            "sku_variant_id": row.sku_variant_id, "status": row.status.value, "submitted_date": row.submitted_date,
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        rows, total = self.repo.catalog_for_vendor(vendor_id, params)
        return [self.to_out(r) for r in rows], total

    def get_for_vendor(self, vendor_id: uuid.UUID, submission_id: uuid.UUID) -> VendorCatalogSubmission:
        row = self.repo.get_catalog_submission(submission_id)
        if not row or row.vendor_id != vendor_id:
            raise NotFoundException("Catalog submission not found")
        return row

    def create(self, vendor_id: uuid.UUID, goods_id: uuid.UUID | None, name: str, product_type: str, gender: str, fabric: str, colour: str, size: str, gsm: int, description: str | None) -> VendorCatalogSubmission:
        row = self.repo.add_catalog_submission(
            VendorCatalogSubmission(
                code=self.repo.next_catalog_code(), vendor_id=vendor_id, goods_id=goods_id, name=name, product_type=product_type, gender=gender,
                fabric=fabric, colour=colour, size=size, gsm=gsm, description=description,
                status=CatalogSubmissionStatus.SUBMITTED,
            )
        )
        self.session.commit()
        return row

    def update(self, vendor_id: uuid.UUID, submission_id: uuid.UUID, **fields) -> VendorCatalogSubmission:
        row = self.get_for_vendor(vendor_id, submission_id)
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        self.session.commit()
        return row

    def upload_documents(self, vendor_id: uuid.UUID, submission_id: uuid.UUID, files: list[UploadFile]) -> list[VendorCatalogDocument]:
        self.get_for_vendor(vendor_id, submission_id)
        storage = get_storage_client()
        docs = []
        for file in files:
            uploaded = storage.save(file, folder="vendor-catalog")
            doc = VendorCatalogDocument(submission_id=submission_id, file_name=uploaded.name, url=uploaded.url)
            self.session.add(doc)
            docs.append(doc)
        self.session.commit()
        return docs

    def list_all(self, params: PaginationParams, search: str | None = None, status: str | None = None):
        return self.repo.list_all_catalog(params, search, status)
