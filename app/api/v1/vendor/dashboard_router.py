from datetime import date, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.dependencies.database import get_db
from app.dependencies.vendor import get_current_vendor
from app.models.payment import Payment, PaymentStatus
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus, Quotation, Rfq, RfqInvitedVendor, RfqStatus
from app.models.shipping import Asn, Invoice, InvoiceStatus, Shipment, ShipmentStatus
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse
from app.services.reports.vendor_report_service import build_vendor_report_sections
from app.utils.date_range import resolve_week_or_month_range
from app.utils.excel_export import build_business_report_workbook

router = APIRouter(prefix="/dashboard", tags=["vendor-dashboard"])

_WINDOW_DAYS = {"week": 7, "month": 30, "year": 365}
# Mirrors QUOTABLE_STATUSES in vms-react's RfqsPage.jsx — RFQs still open for a vendor to quote against.
_QUOTABLE_RFQ_STATUSES = (RfqStatus.SENT, RfqStatus.AWAITING_QUOTATIONS, RfqStatus.PARTIALLY_RESPONDED)


def _period_start(period: str) -> date:
    return date.today() - timedelta(days=_WINDOW_DAYS.get(period, 30))


@router.get("/kpis", response_model=ApiResponse[dict])
def get_kpis(period: str = "month", vendor: Vendor = Depends(get_current_vendor), session=Depends(get_db)):
    start = _period_start(period)

    already_quoted = select(Quotation.rfq_id).where(Quotation.vendor_id == vendor.id)
    available_rfqs_query = (
        select(Rfq)
        .join(RfqInvitedVendor, RfqInvitedVendor.rfq_id == Rfq.id)
        .where(
            RfqInvitedVendor.vendor_id == vendor.id,
            Rfq.status.in_(_QUOTABLE_RFQ_STATUSES),
            Rfq.id.not_in(already_quoted),
        )
    )
    available_rfqs_total = session.execute(
        select(func.count()).select_from(available_rfqs_query.subquery())
    ).scalar_one()
    available_rfqs_new = session.execute(
        select(func.count()).select_from(available_rfqs_query.where(Rfq.created_at >= start).subquery())
    ).scalar_one()

    submitted_quotes_total = session.execute(
        select(func.count()).select_from(Quotation).where(Quotation.vendor_id == vendor.id)
    ).scalar_one()
    submitted_quotes_new = session.execute(
        select(func.count()).select_from(Quotation).where(Quotation.vendor_id == vendor.id, Quotation.submitted_date >= start)
    ).scalar_one()

    accepted_statuses = (PurchaseOrderStatus.ACCEPTED, PurchaseOrderStatus.IN_PRODUCTION, PurchaseOrderStatus.READY_TO_SHIP, PurchaseOrderStatus.DELIVERED)
    accepted_pos_total = session.execute(
        select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.vendor_id == vendor.id, PurchaseOrder.status.in_(accepted_statuses))
    ).scalar_one()
    accepted_pos_new = session.execute(
        select(func.count()).select_from(PurchaseOrder)
        .where(PurchaseOrder.vendor_id == vendor.id, PurchaseOrder.status.in_(accepted_statuses), PurchaseOrder.created_at >= start)
    ).scalar_one()

    # Shipment doesn't carry vendor_id directly — go through its Asn -> PurchaseOrder.
    pending_shipment_statuses = (ShipmentStatus.PACKED, ShipmentStatus.DISPATCHED, ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELAYED)
    pending_shipments_total = session.execute(
        select(func.count()).select_from(Shipment)
        .join(Asn, Asn.id == Shipment.asn_id)
        .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
        .where(PurchaseOrder.vendor_id == vendor.id, Shipment.status.in_(pending_shipment_statuses))
    ).scalar_one()
    delayed_shipments = session.execute(
        select(func.count()).select_from(Shipment)
        .join(Asn, Asn.id == Shipment.asn_id)
        .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
        .where(PurchaseOrder.vendor_id == vendor.id, Shipment.status == ShipmentStatus.DELAYED)
    ).scalar_one()

    pending_payments_total, pending_payments_amount = session.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount), 0))
        .select_from(Payment)
        .join(PurchaseOrder, PurchaseOrder.id == Payment.po_id)
        .where(PurchaseOrder.vendor_id == vendor.id, Payment.status == PaymentStatus.PENDING)
    ).one()

    invoices_due_total, invoices_due_amount = session.execute(
        select(func.count(), func.coalesce(func.sum(Invoice.total_amount), 0))
        .where(Invoice.vendor_id == vendor.id, Invoice.status == InvoiceStatus.PENDING)
    ).one()

    return ApiResponse(data={
        "available_rfqs": {"total": available_rfqs_total, "new_this_period": available_rfqs_new},
        "submitted_quotes": {"total": submitted_quotes_total, "new_this_period": submitted_quotes_new},
        "accepted_pos": {"total": accepted_pos_total, "new_this_period": accepted_pos_new},
        "pending_shipments": {"total": pending_shipments_total, "delayed": delayed_shipments},
        "pending_payments": {"total": pending_payments_total, "amount": float(pending_payments_amount)},
        "invoices_due": {"total": invoices_due_total, "amount": float(invoices_due_amount)},
    })


@router.get("/graphs/revenue", response_model=ApiResponse[dict])
def get_revenue_graph(period: str = "month", vendor: Vendor = Depends(get_current_vendor), session=Depends(get_db)):
    """Cumulative revenue from this vendor's accepted invoices over the given window."""
    start = _period_start(period)

    invoices = session.execute(
        select(Invoice)
        .where(Invoice.vendor_id == vendor.id, Invoice.status == InvoiceStatus.ACCEPTED, Invoice.invoice_date >= start)
        .order_by(Invoice.invoice_date)
    ).scalars().all()

    series = []
    cumulative = 0.0
    for invoice in invoices:
        cumulative += float(invoice.total_amount)
        series.append({"date": invoice.invoice_date.isoformat(), "cumulative_revenue": round(cumulative, 2)})

    total_amount = sum(float(invoice.total_amount) for invoice in invoices)
    average_invoice_value = total_amount / len(invoices) if invoices else 0

    # Growth: revenue in the second half of the window vs. the first half.
    midpoint = len(invoices) // 2
    first_half_total = sum(float(invoice.total_amount) for invoice in invoices[:midpoint])
    second_half_total = sum(float(invoice.total_amount) for invoice in invoices[midpoint:])
    growth_percent = round((second_half_total - first_half_total) / first_half_total * 100, 1) if first_half_total else 0

    return ApiResponse(data={"series": series, "growth_percent": growth_percent, "average_invoice_value": round(average_invoice_value, 2)})


@router.get("/export-report")
def export_report(
    mode: str, date: date, vendor: Vendor = Depends(get_current_vendor), session=Depends(get_db),
):
    start, end, period_label = resolve_week_or_month_range(mode, date)
    sections = build_vendor_report_sections(session, vendor.id, start, end)
    details = {
        "Vendor Code": vendor.code, "Name": vendor.name, "Contact Person": vendor.contact_person,
        "Email": vendor.contact_email, "Phone": vendor.contact_phone, "GST": vendor.gst,
        "Address": vendor.address, "City": vendor.city, "State": vendor.state,
    }
    buffer = build_business_report_workbook(
        "Vendor", details, period_label, sections,
        show_logo=False, subtitle="Vendor Management Portal", center_align=True,
    )
    filename = f"vendor_report_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
