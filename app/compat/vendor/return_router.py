"""Vendor returns compat. Confirmed against src/pages/ReturnsPage.jsx: the vendor reviews
(approve/reject) the return request and later creates the return shipment themselves -- but the
real VendorReturnService.approve/reject/schedule_pickup/dispatch methods are all warehouse_id-
scoped (see app/services/vendor/vendor_return_service.py's own docstring: "warehouse review,
vendor pickup/dispatch, completion" -- the real backend's workflow puts the *review* step on the
warehouse side, not the vendor). Rather than force a warehouse_id through a vendor token, this
performs the same field/status transitions warehouse's approve/reject/schedule_pickup/dispatch
already do, just looked up through VendorReturnRepository.get_for_vendor (already used elsewhere
in this codebase) instead of get_for_warehouse. `complete()` is reused unchanged since it's
already vendor-scoped in the real service.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.compat.schemas import CamelModel
from app.compat.vendor.common import dec, envelope, iso, paginate_list, vendor_meta
from app.compat.vendor.freight_payment_router import freight_payment_out
from app.compat.vendor.rfq_router import _sku_variant_out
from app.core.exceptions import ConflictException, NotFoundException
from app.dependencies.vendor import get_current_vendor, get_vendor_return_service
from app.models.payment import FreightPayment
from app.models.procurement import PurchaseOrder
from app.models.shipping import Asn
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.vendor_return_service import VendorReturnService

router = APIRouter(prefix="/returns", tags=["vendor-compat-returns"])

_ALL = PaginationParams(page=1, limit=100000)


def _freight_for_return(session, return_id):
    row = session.execute(select(FreightPayment).where(FreightPayment.linked_type == "vendor_return", FreightPayment.linked_id == return_id)).scalar_one_or_none()
    return freight_payment_out(row) if row else None


def _return_out(session, row, with_details: bool) -> dict:
    from app.repositories.vendor_return_repository import VendorReturnRepository

    po = session.get(PurchaseOrder, row.po_id)
    asn = session.get(Asn, row.asn_id)
    attachments = VendorReturnRepository(session).attachments_for_return(row.id)
    out = {
        "id": str(row.id),
        "refCode": row.ref_code,
        "poId": str(row.po_id),
        "poRefCode": po.ref_code if po else None,
        "asnId": str(row.asn_id),
        "asnRefCode": asn.ref_code if asn else None,
        "qty": row.qty,
        "skuVariant": _sku_variant_out(session, row.sku_variant_id),
        "reason": row.reason,
        "refundAmount": dec(row.refund_amount),
        "status": row.status.value,
        "reviewRemarks": row.review_remarks,
        "pickupDate": iso(row.pickup_date),
        "transporter": row.transporter,
        "driverName": row.driver_name,
        "driverContact": row.driver_contact,
        "vehicleNo": row.vehicle_no,
        "trackingNo": row.tracking_no,
        "shipmentRemarks": None,  # genuine gap: no backing column on VendorReturn
        "attachments": [{"id": str(a.id), "fileName": a.file_name} for a in attachments],
    }
    if with_details:
        out["freightPayment"] = _freight_for_return(session, row.id)
    return out


class ReviewRequest(CamelModel):
    review_remarks: str | None = None


class CreateReturnShipmentRequest(CamelModel):
    pickup_date: str
    transporter: str
    driver_name: str | None = None
    driver_contact: str | None = None
    vehicle_no: str | None = None
    tracking_no: str | None = None
    shipment_remarks: str | None = None


@router.get("")
def list_returns(page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, status)
    items = [_return_out(service.session, r, with_details=False) for r in rows]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["refCode"] or "").lower() or q in (i["reason"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/{return_id}")
def get_return(return_id: str, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.repo.get_for_vendor(vendor.id, return_id)
    if not row:
        raise NotFoundException("Vendor return not found")
    return envelope(_return_out(service.session, row, with_details=True))


@router.get("/{return_id}/attachments/{attachment_id}")
def get_return_attachment(return_id: str, attachment_id: str, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.repo.get_for_vendor(vendor.id, return_id)
    if not row:
        raise NotFoundException("Vendor return not found")
    attachment = service.repo.get_attachment(return_id, attachment_id)
    if not attachment:
        raise NotFoundException("Attachment not found")
    from app.compat.vendor.common import redirect_to_file

    return redirect_to_file(attachment.url)


@router.patch("/{return_id}/approve")
def approve_return(return_id: str, body: ReviewRequest, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.repo.get_for_vendor(vendor.id, return_id)
    if not row:
        raise NotFoundException("Vendor return not found")
    if row.status.value != "Initiated":
        raise ConflictException(f"Cannot approve a return with status '{row.status.value}'")
    row.status = "Approved"
    row.review_remarks = body.review_remarks
    service.session.commit()
    return envelope(_return_out(service.session, row, with_details=False))


@router.patch("/{return_id}/reject")
def reject_return(return_id: str, body: ReviewRequest, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.repo.get_for_vendor(vendor.id, return_id)
    if not row:
        raise NotFoundException("Vendor return not found")
    if row.status.value != "Initiated":
        raise ConflictException(f"Cannot reject a return with status '{row.status.value}'")
    row.status = "Rejected"
    row.review_remarks = body.review_remarks
    service.session.commit()
    return envelope(_return_out(service.session, row, with_details=False))


@router.patch("/{return_id}/shipment")
def create_return_shipment(return_id: str, body: CreateReturnShipmentRequest, service: VendorReturnService = Depends(get_vendor_return_service), vendor: Vendor = Depends(get_current_vendor)):
    from datetime import datetime

    row = service.repo.get_for_vendor(vendor.id, return_id)
    if not row:
        raise NotFoundException("Vendor return not found")
    if row.status.value != "Approved":
        raise ConflictException(f"Cannot create a shipment for a return with status '{row.status.value}'")
    row.pickup_date = datetime.strptime(body.pickup_date, "%Y-%m-%d").date()
    row.transporter = body.transporter
    row.driver_name = body.driver_name
    row.driver_contact = body.driver_contact
    row.vehicle_no = body.vehicle_no
    row.tracking_no = body.tracking_no
    row.status = "In Transit"
    service.session.commit()
    return envelope(_return_out(service.session, row, with_details=False))
