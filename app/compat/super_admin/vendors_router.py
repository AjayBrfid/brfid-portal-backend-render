"""vms-sa-react's original Vendor Approval + Vendor Detail contract, mounted flat at
`/api/v1/vendors...` (see BACKEND_API_SPEC.md). Approve/reject/block/unblock/set-password all
call straight through to AdminVendorService — the exact same service the real
`/api/v1/super-admin/vendors...` routes use — so there is exactly one place state-transition
rules and audit logging live. The only new code here is presentation: pulling a few extra
columns directly off the Vendor row and two simple counts (`totalPOs`/`totalQuotations`)
against PurchaseOrder/Quotation, since AdminVendorService's own `_to_out` never needed them.
"""
import mimetypes

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import RejectBody, SetPasswordBody, VendorOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.super_admin import get_admin_vendor_service
from app.models.procurement import PurchaseOrder, Quotation
from app.models.user import User
from app.models.vendor import ComplianceDocType, Vendor, VendorComplianceDocument
from app.schemas.common import ApiResponse, PaginationParams
from app.services.super_admin.vendor_admin_service import AdminVendorService
from app.utils.storage import get_storage_client

router = APIRouter(prefix="/vendors", tags=["super-admin-compat-vendors"])
_portal = require_portal("super_admin")


def _vendor_to_out(session: Session, vendor: Vendor) -> dict:
    total_pos = session.execute(
        select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.vendor_id == vendor.id)
    ).scalar_one()
    total_quotations = session.execute(
        select(func.count()).select_from(Quotation).where(Quotation.vendor_id == vendor.id)
    ).scalar_one()
    docs = session.execute(
        select(VendorComplianceDocument)
        .where(VendorComplianceDocument.vendor_id == vendor.id)
        .order_by(VendorComplianceDocument.uploaded_at)
    ).scalars().all()
    compliance = {doc_type.value: {"uploaded": False, "url": None} for doc_type in ComplianceDocType}
    for doc in docs:
        # `url` is a path the frontend's authenticated apiClient can GET directly (see
        # openAuthedFile() in vms-sa-react/src/lib/apiClient.js) -- NOT the raw storage key,
        # which isn't a viewable link on its own (S3-compatible storage never makes this
        # bucket public-read; see app/utils/storage.py's S3StorageClient docstring).
        compliance[doc.doc_type.value] = {"uploaded": True, "url": f"/vendors/{vendor.code}/compliance-documents/{doc.doc_type.value}"}
    return {
        "id": vendor.code, "name": vendor.name, "category": vendor.category, "contact_person": vendor.contact_person,
        "email": vendor.contact_email, "phone": vendor.contact_phone, "city": vendor.city, "state": vendor.state,
        "gst": vendor.gst, "registered_on": vendor.registered_on.date(), "status": vendor.status.value,
        "rating": float(vendor.rating) if vendor.rating else None, "total_pos": total_pos,
        "total_quotations": total_quotations, "compliance": compliance,
    }


def _get_vendor_or_404(service: AdminVendorService, vendor_id: str) -> Vendor:
    vendor = service.repo.get_by_code(vendor_id)
    if not vendor:
        raise NotFoundException(f"Vendor '{vendor_id}' not found")
    return vendor


@router.get("", response_model=ApiResponse[list[VendorOut]])
def list_vendors(
    search: str | None = None, status: str | None = None, sort: str | None = None, order: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db),
    service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal),
):
    rows, total = service.repo.list_all(params, search, status, sort, order)
    items = [_vendor_to_out(session, v) for v in rows]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def vendor_stats(service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.stats())


@router.get("/{vendor_id}", response_model=ApiResponse[VendorOut])
def get_vendor(
    vendor_id: str, session: Session = Depends(get_db),
    service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal),
):
    vendor = _get_vendor_or_404(service, vendor_id)
    return ApiResponse(data=_vendor_to_out(session, vendor))


@router.get("/{vendor_id}/compliance-documents/{doc_type}")
def get_vendor_compliance_document(
    vendor_id: str, doc_type: str, session: Session = Depends(get_db),
    service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal),
):
    vendor = _get_vendor_or_404(service, vendor_id)
    doc = session.execute(
        select(VendorComplianceDocument).where(
            VendorComplianceDocument.vendor_id == vendor.id, VendorComplianceDocument.doc_type == doc_type,
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundException("Compliance document not found")
    content_type = mimetypes.guess_type(doc.url)[0] or "application/octet-stream"
    return Response(content=get_storage_client().read(doc.url), media_type=content_type)


@router.post("/{vendor_id}/approve", response_model=ApiResponse[dict])
def approve_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.approve(vendor_id, admin))


@router.post("/{vendor_id}/reject", response_model=ApiResponse[dict])
def reject_vendor(vendor_id: str, body: RejectBody, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.reject(vendor_id, admin, body.reason))


@router.post("/{vendor_id}/block", response_model=ApiResponse[dict])
def block_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.block(vendor_id, admin))


@router.post("/{vendor_id}/unblock", response_model=ApiResponse[dict])
def unblock_vendor(vendor_id: str, service: AdminVendorService = Depends(get_admin_vendor_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.unblock(vendor_id, admin))


@router.put("/{vendor_id}/password", response_model=ApiResponse[dict])
def set_vendor_password(vendor_id: str, body: SetPasswordBody, service: AdminVendorService = Depends(get_admin_vendor_service), _: User = Depends(_portal)):
    service.set_vendor_password(vendor_id, body.new_password)
    return ApiResponse(data={})
