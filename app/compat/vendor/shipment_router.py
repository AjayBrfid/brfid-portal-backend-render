"""Shipments (Deliveries page) compat. Confirmed against src/pages/DeliveriesPage.jsx: the
frontend expects driverName/driverContact/packages/weight (present on the real Shipment model
but dropped by the real vendor router's flat _to_out), plus poRefCode/asnRefCode companions and
a nested `freightPayment` object (see FreightCard.jsx) -- all built here directly from the same
ShipmentRepository/Shipment model already used by app/api/v1/vendor/shipment_router.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.compat.schemas import CamelModel
from app.compat.vendor.common import dec, envelope, iso, paginate_list, vendor_meta
from app.compat.vendor.freight_payment_router import freight_payment_out
from app.dependencies.vendor import get_current_vendor, get_shipment_service
from app.models.payment import FreightPayment
from app.models.procurement import PurchaseOrder
from app.models.shipping import Asn
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.shipment_service import ShipmentService

router = APIRouter(prefix="/shipments", tags=["vendor-compat-shipments"])

_ALL = PaginationParams(page=1, limit=100000)


def _freight_for_shipment(session, shipment_id):
    row = session.execute(select(FreightPayment).where(FreightPayment.linked_type == "shipment", FreightPayment.linked_id == shipment_id)).scalar_one_or_none()
    return freight_payment_out(row) if row else None


def _shipment_out(session, repo, shipment, with_details: bool) -> dict:
    asn = session.get(Asn, shipment.asn_id)
    po = session.get(PurchaseOrder, asn.po_id) if asn else None
    out = {
        "id": str(shipment.id),
        "asnId": str(shipment.asn_id),
        "asnRefCode": asn.ref_code if asn else None,
        "poId": str(po.id) if po else None,
        "poRefCode": po.ref_code if po else None,
        "dispatchDate": iso(shipment.dispatch_date),
        "expectedDelivery": iso(shipment.expected_delivery),
        "transporter": shipment.transporter,
        "driverName": shipment.driver_name,
        "driverContact": shipment.driver_contact,
        "vehicleNo": shipment.vehicle_no,
        "trackingNo": shipment.tracking_no,
        "packages": shipment.packages,
        "weight": dec(shipment.weight),
        "notes": shipment.notes,
        "status": shipment.status.value,
    }
    if with_details:
        out["timeline"] = [{"status": e.status, "occurredAt": iso(e.occurred_at), "remarks": e.remarks} for e in repo.timeline_for_shipment(shipment.id)]
        out["freightPayment"] = _freight_for_shipment(session, shipment.id)
    return out


class ShipmentCreateRequest(CamelModel):
    asn_id: str
    dispatch_date: str
    transporter: str
    driver_name: str | None = None
    driver_contact: str | None = None
    vehicle_no: str | None = None
    tracking_no: str | None = None
    packages: int | None = None


class ShipmentStatusUpdateRequest(CamelModel):
    status: str
    remarks: str | None = None


@router.get("")
def list_shipments(page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL)
    items = [_shipment_out(service.session, service.repo, s, with_details=False) for s in rows]
    if status:
        items = [i for i in items if i["status"] == status]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["trackingNo"] or "").lower() or q in (i["transporter"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/{shipment_id}")
def get_shipment(shipment_id: str, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    shipment = service.repo.get_for_vendor(vendor.id, shipment_id)
    if not shipment:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Shipment not found")
    return envelope(_shipment_out(service.session, service.repo, shipment, with_details=True))


@router.post("", status_code=201)
def create_shipment(body: ShipmentCreateRequest, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    from datetime import datetime

    dispatch_date = datetime.strptime(body.dispatch_date, "%Y-%m-%d").date()
    shipment = service.create_shipment(
        vendor.id, body.asn_id, dispatch_date, None, body.transporter, body.driver_name,
        body.driver_contact, body.vehicle_no, body.tracking_no, None, body.packages, None,
    )
    return envelope(_shipment_out(service.session, service.repo, shipment, with_details=True))


@router.patch("/{shipment_id}/status")
def update_shipment_status(shipment_id: str, body: ShipmentStatusUpdateRequest, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    service.update_status(vendor.id, shipment_id, body.status, body.remarks)
    shipment = service.repo.get_for_vendor(vendor.id, shipment_id)
    return envelope(_shipment_out(service.session, service.repo, shipment, with_details=True))
