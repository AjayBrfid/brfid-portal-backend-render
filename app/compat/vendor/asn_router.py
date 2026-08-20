"""ASN compat. Per the corrected ground truth (coordinator's message + direct read of
src/services/api/asn.js and src/pages/CreateAsnPage.jsx), this entire module deviates from
API_SPECIFICATION.md: `POST /purchase-orders/:poId/asn` and `PUT /asn/:id` both take multipart
with a JSON `payload` field (shippedQty/expectedDeliveryDate/draftStatus/batchNo, plus nested
shipment/freight/invoice objects required when draftStatus is "Submitted") and an optional
`invoicePdf` file -- the frontend's comment says the ASN, its shipment, freight, and invoice are
"all created together in one backend transaction". The real backend has no single service call
for that combination, so this orchestrates the existing AsnService/ShipmentService/InvoiceService
(plus a direct FreightPayment insert, mirroring exactly what ShipmentService.update_status does
on delivery) in sequence -- still no new business rules, just sequencing existing ones.
"""
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select

from app.compat.vendor.common import dec, envelope, iso, paginate_list, vendor_meta
from app.core.exceptions import BadRequestException, NotFoundException
from app.dependencies.vendor import get_asn_service, get_current_vendor, get_purchase_order_service
from app.models.payment import FreightDirection, FreightLinkedType, FreightPayment
from app.models.procurement import PurchaseOrder
from app.models.shipping import Invoice, Shipment
from app.models.vendor import Vendor
from app.repositories.payment_repository import FreightPaymentRepository
from app.schemas.common import PaginationParams
from app.services.vendor.asn_service import AsnService
from app.services.vendor.invoice_service import InvoiceService
from app.services.vendor.purchase_order_service import PurchaseOrderService
from app.services.vendor.shipment_service import ShipmentService
from app.utils.storage import get_storage_client

router = APIRouter(tags=["vendor-compat-asn"])

_ALL = PaginationParams(page=1, limit=100000)


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _dec_or(value, default="0") -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else Decimal(default)
    except InvalidOperation:
        return Decimal(default)


def _asn_out(session, asn) -> dict:
    from app.models.shipping import AsnItem
    from app.services.vendor.asn_service import AsnService

    po = session.get(PurchaseOrder, asn.po_id)
    items = session.scalars(select(AsnItem).where(AsnItem.asn_id == asn.id)).all()
    # inspectionStatus/rejectionReason tell CreateAsnPage.jsx whether this ASN is locked
    # (awaiting_inspection/accepted) or open for a vendor correction (partial/rejected) — see
    # AsnService._to_out for the same status derivation the warehouse side already relies on.
    receipt = AsnService(session).repo.get_goods_receipt(asn.id)
    shipment = session.execute(select(Shipment).where(Shipment.asn_id == asn.id)).scalar_one_or_none()
    invoice = session.execute(select(Invoice).where(Invoice.asn_id == asn.id)).scalar_one_or_none()
    freight = None
    if shipment:
        freight = session.execute(
            select(FreightPayment).where(FreightPayment.linked_type == FreightLinkedType.SHIPMENT, FreightPayment.linked_id == shipment.id)
        ).scalar_one_or_none()
    return {
        "id": str(asn.id),
        "refCode": asn.ref_code,
        "poId": str(asn.po_id),
        "poRefCode": po.ref_code if po else None,
        "shippedQty": asn.shipped_qty,
        "expectedDeliveryDate": iso(asn.expected_delivery_date),
        "draftStatus": asn.draft_status.value,
        "transportCharge": dec(asn.transport_charge),
        "createdDate": iso(asn.created_date),
        "inspectionStatus": receipt.inspection_status.value if receipt else "awaiting_inspection",
        "acceptedQty": receipt.accepted_qty if receipt else None,
        "rejectedQty": receipt.rejected_qty if receipt else None,
        "rejectionReason": receipt.rejection_reason if receipt else None,
        "items": [
            {"skuVariantId": str(i.sku_variant_id) if i.sku_variant_id else None, "orderedQty": i.ordered_qty, "shippedQty": i.shipped_qty, "batchNo": i.batch_no}
            for i in items
        ],
        # Pre-fills the correction form (needsCorrection) with the vendor's own last-submitted
        # shipment/freight/invoice details rather than reopening a blank form.
        "shipment": {
            "dispatchDate": iso(shipment.dispatch_date), "transporter": shipment.transporter,
            "driverName": shipment.driver_name, "driverContact": shipment.driver_contact,
            "vehicleNo": shipment.vehicle_no, "trackingNo": shipment.tracking_no, "packages": shipment.packages,
        } if shipment else None,
        "freight": {
            "payer": freight.payer.value, "baseFreight": dec(freight.base_freight), "gstOnFreight": dec(freight.gst_on_freight),
        } if freight else None,
        "invoice": {
            "invoiceNumber": invoice.invoice_number, "invoiceDate": iso(invoice.invoice_date),
            "dueDate": iso(invoice.due_date), "baseAmount": dec(invoice.base_amount), "gstAmount": dec(invoice.gst_amount),
            "discountAmount": dec(invoice.discount_amount), "totalAmount": dec(invoice.total_amount),
        } if invoice else None,
    }


def _get_owned_asn(service: AsnService, vendor_id, asn_id):
    # Reuses AsnService's own vendor-ownership check (it already resolves the ASN's PO and
    # verifies po.vendor_id == vendor_id) rather than re-querying that same join here.
    return service._get_asn_for_vendor(vendor_id, asn_id)


def _apply_asn_payload(session, vendor: Vendor, po: PurchaseOrder, asn, payload: dict, invoice_pdf):
    if payload.get("shippedQty") is not None:
        asn.shipped_qty = int(payload["shippedQty"])
    if "expectedDeliveryDate" in payload:
        asn.expected_delivery_date = _parse_date(payload.get("expectedDeliveryDate"))
    batch_no = payload.get("batchNo")
    if batch_no:
        from app.models.shipping import AsnItem

        for item in session.scalars(select(AsnItem).where(AsnItem.asn_id == asn.id)):
            item.batch_no = batch_no

    if payload.get("draftStatus") == "Submitted":
        AsnService(session).submit_asn(vendor.id, asn.id)

        shipment_data = payload.get("shipment") or {}
        existing_shipment = session.execute(select(Shipment).where(Shipment.asn_id == asn.id)).scalar_one_or_none()
        if not existing_shipment and shipment_data:
            shipment = ShipmentService(session).create_shipment(
                vendor.id, asn.id, _parse_date(shipment_data.get("dispatchDate")) or date.today(), asn.expected_delivery_date,
                shipment_data.get("transporter") or "", shipment_data.get("driverName"), shipment_data.get("driverContact"),
                shipment_data.get("vehicleNo"), shipment_data.get("trackingNo"), None, shipment_data.get("packages"), None,
            )
            freight_data = payload.get("freight") or {}
            base_freight = _dec_or(freight_data.get("baseFreight"))
            gst_on_freight = _dec_or(freight_data.get("gstOnFreight"))
            FreightPaymentRepository(session).add(
                FreightPayment(
                    direction=FreightDirection.VENDOR_TO_WAREHOUSE, linked_type=FreightLinkedType.SHIPMENT, linked_id=shipment.id,
                    transporter=shipment.transporter, payer=freight_data.get("payer") or "vendor",
                    base_freight=base_freight, gst_on_freight=gst_on_freight,
                    net_payable_to_transporter=base_freight + gst_on_freight, final_liability_amount=base_freight + gst_on_freight,
                )
            )

        invoice_data = payload.get("invoice") or {}
        existing_invoice = session.execute(select(Invoice).where(Invoice.asn_id == asn.id)).scalar_one_or_none()
        if not existing_invoice and invoice_data.get("invoiceNumber"):
            # Base/GST amounts are ALWAYS derived server-side from the PO's own locked
            # unit_price/discount_percent/tax_percent and this ASN's shipped_qty — never from
            # whatever the client submits. Trusting a client-supplied baseAmount/gstAmount here
            # would let a vendor bill any price they like, unrelated to what was actually
            # quoted and accepted on the RFQ.
            base_amount = round(asn.shipped_qty * po.unit_price * (1 - po.discount_percent / 100), 2)
            gst_amount = round(base_amount * (po.tax_percent / 100), 2)
            invoice = InvoiceService(session).create_invoice(
                vendor.id, po.id, asn.id, invoice_data["invoiceNumber"], _parse_date(invoice_data.get("invoiceDate")) or date.today(),
                _parse_date(invoice_data.get("dueDate")), base_amount, gst_amount,
                _dec_or(invoice_data.get("discountAmount")), _dec_or(invoice_data.get("freightAmount")),
            )
            if invoice_pdf is not None:
                uploaded = get_storage_client().save(invoice_pdf, folder="vendor-invoices")
                invoice.pdf_url = uploaded.url

    session.commit()


@router.get("/asn")
def list_asns(
    page: int = 1, limit: int = 20, draft_status: str | None = None, po_id: str | None = None,
    service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor),
):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL)
    items = [_asn_out(service.session, a) for a in rows]
    if draft_status:
        items = [i for i in items if i["draftStatus"] == draft_status]
    if po_id:
        items = [i for i in items if i["poId"] == po_id]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/asn/{asn_id}")
def get_asn(asn_id: str, service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor)):
    asn = _get_owned_asn(service, vendor.id, asn_id)
    return envelope(_asn_out(service.session, asn))


@router.post("/purchase-orders/{po_id}/asn", status_code=201)
def create_asn(
    po_id: str, payload: str = Form(...), invoice_pdf: UploadFile | None = File(None, alias="invoicePdf"),
    service: AsnService = Depends(get_asn_service), po_service: PurchaseOrderService = Depends(get_purchase_order_service),
    vendor: Vendor = Depends(get_current_vendor),
):
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BadRequestException("`payload` must be valid JSON") from exc

    po = po_service.get_for_vendor(vendor.id, po_id)
    asn = service.create_asn(vendor.id, po_id, int(data.get("shippedQty") or 0), _parse_date(data.get("expectedDeliveryDate")), None)
    _apply_asn_payload(service.session, vendor, po, asn, data, invoice_pdf)
    return envelope(_asn_out(service.session, asn))


@router.post("/asn/{asn_id}/resubmit")
def resubmit_asn(
    asn_id: str, payload: str = Form(...),
    service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor),
):
    """The vendor's correction path after a partial/full rejection — CreateAsnPage.jsx reopens
    the same ASN's full shipment/transport/freight fields (not just qty/date/batch) and posts
    the corrected shipment here, since a replacement delivery is its own trip with its own
    dispatch date, transporter, driver, vehicle, tracking, and freight arrangement rather than
    filing a brand new ASN (create_asn refuses a second one for the same PO)."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BadRequestException("`payload` must be valid JSON") from exc

    shipment_data = data.get("shipment") or {}
    freight_data = data.get("freight") or {}
    asn = service.resubmit_after_rejection(
        vendor.id, asn_id, int(data.get("shippedQty") or 0), _parse_date(data.get("expectedDeliveryDate")), data.get("batchNo"),
        shipment_data={
            "dispatch_date": _parse_date(shipment_data.get("dispatchDate")),
            "transporter": shipment_data.get("transporter"),
            "driver_name": shipment_data.get("driverName"),
            "driver_contact": shipment_data.get("driverContact"),
            "vehicle_no": shipment_data.get("vehicleNo"),
            "tracking_no": shipment_data.get("trackingNo"),
            "packages": shipment_data.get("packages"),
        } if shipment_data else None,
        freight_data={
            "payer": freight_data.get("payer"),
            "base_freight": _dec_or(freight_data.get("baseFreight")),
            "gst_on_freight": _dec_or(freight_data.get("gstOnFreight")),
        } if freight_data else None,
    )
    return envelope(_asn_out(service.session, asn))


@router.put("/asn/{asn_id}")
def update_asn(
    asn_id: str, payload: str = Form(...), invoice_pdf: UploadFile | None = File(None, alias="invoicePdf"),
    service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor),
):
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BadRequestException("`payload` must be valid JSON") from exc

    asn = _get_owned_asn(service, vendor.id, asn_id)
    po = service.session.get(PurchaseOrder, asn.po_id)
    _apply_asn_payload(service.session, vendor, po, asn, data, invoice_pdf)
    return envelope(_asn_out(service.session, asn))


@router.post("/asn/{asn_id}/attachments", status_code=201)
def upload_asn_attachment(
    asn_id: str, file: UploadFile = File(...), remark: str | None = Form(None),
    service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor),
):
    _get_owned_asn(service, vendor.id, asn_id)
    uploaded = get_storage_client().save(file, folder="asn-attachments")
    attachment = service.upload_attachment(asn_id, uploaded.name, uploaded.url, remark, "vendor")
    return envelope({"id": str(attachment.id), "fileName": attachment.file_name, "remark": attachment.remark})
