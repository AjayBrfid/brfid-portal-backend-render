"""vms-sa-react's Vendor Catalog review contract (`/vendor-catalog...`). List/stats/detail reuse
CatalogService.list_all — the same listing logic the real `/api/v1/super-admin/vendor-catalog`
route already calls — reshaped with vendor name, attached documents, and the assigned SKU code.
`generate-sku` calls straight through to AdminVendorService.generate_sku (the real SKU-creation
logic, unchanged); the old contract's optional `{"sku": "..."}` override doesn't map cleanly onto
the real service's optional `style_code` + optional hsn/gst_rate/mrp, so hsn/gst_rate/mrp are left
null (the old frontend never collects them) and the style code is left for the service to
auto-assign (SKU-001, SKU-002, ...) whenever the caller doesn't supply one."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import GenerateSkuBody, GenerateSkuOut, VendorCatalogOut
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.super_admin import get_admin_vendor_service
from app.models.catalog import SkuVariant
from app.models.user import User
from app.models.vendor import Vendor, VendorCatalogDocument, VendorCatalogSubmission
from app.schemas.common import ApiResponse, PaginationParams
from app.services.super_admin.vendor_admin_service import AdminVendorService
from app.services.vendor.catalog_service import CatalogService

router = APIRouter(prefix="/vendor-catalog", tags=["super-admin-compat-vendor-catalog"])
_portal = require_portal("super_admin")


def _reshape(session: Session, rows: list[VendorCatalogSubmission]) -> list[dict]:
    vendor_ids = {r.vendor_id for r in rows}
    vendors = {v.id: v for v in session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars()} if vendor_ids else {}

    variant_ids = {r.sku_variant_id for r in rows if r.sku_variant_id}
    variants = {v.id: v for v in session.execute(select(SkuVariant).where(SkuVariant.id.in_(variant_ids))).scalars()} if variant_ids else {}

    submission_ids = [r.id for r in rows]
    docs_by_submission: dict = {sid: [] for sid in submission_ids}
    if submission_ids:
        docs = session.execute(
            select(VendorCatalogDocument).where(VendorCatalogDocument.submission_id.in_(submission_ids))
        ).scalars().all()
        for doc in docs:
            docs_by_submission.setdefault(doc.submission_id, []).append(doc)

    items = []
    for r in rows:
        vendor = vendors.get(r.vendor_id)
        variant = variants.get(r.sku_variant_id) if r.sku_variant_id else None
        items.append({
            "id": r.id, "code": r.code, "vendor_id": vendor.code if vendor else None, "vendor_name": vendor.name if vendor else None,
            "name": r.name, "product_type": r.product_type, "gender": r.gender, "fabric": r.fabric,
            "colour": r.colour, "size": r.size, "gsm": r.gsm, "description": r.description,
            "sku": variant.variant_code if variant else None, "submitted_date": r.submitted_date.date(),
            "documents": [{"name": d.file_name, "uploaded_date": d.uploaded_date.date(), "url": d.url} for d in docs_by_submission.get(r.id, [])],
            "status": r.status.value,
        })
    return items


@router.get("", response_model=ApiResponse[list[VendorCatalogOut]])
def list_vendor_catalog(
    search: str | None = None, status: str | None = None, params: PaginationParams = Depends(),
    session: Session = Depends(get_db), _: User = Depends(_portal),
):
    rows, total = CatalogService(session).list_all(params, search, status)
    return ApiResponse(data=_reshape(session, rows), meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def vendor_catalog_stats(session: Session = Depends(get_db), _: User = Depends(_portal)):
    rows = session.execute(
        select(VendorCatalogSubmission.status, func.count()).group_by(VendorCatalogSubmission.status)
    ).all()
    return ApiResponse(data={status.value: count for status, count in rows})


@router.get("/{submission_id}", response_model=ApiResponse[VendorCatalogOut])
def get_vendor_catalog(
    submission_id: str, session: Session = Depends(get_db),
    service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal),
):
    row = service.get_vendor_catalog_submission(submission_id)
    return ApiResponse(data=_reshape(session, [row])[0])


@router.post("/{submission_id}/generate-sku", response_model=ApiResponse[GenerateSkuOut])
def generate_sku(
    submission_id: str, body: GenerateSkuBody,
    service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal),
):
    result = service.generate_sku(submission_id, admin, body.sku or None, None, None, None)
    return ApiResponse(data={
        "sku": result["variant_code"], "assigned_submission_ids": [str(submission_id)], "assigned_count": 1,
    })
