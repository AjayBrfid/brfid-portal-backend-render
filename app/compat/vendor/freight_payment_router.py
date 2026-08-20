"""Freight/transport payments compat. Confirmed against src/components/FreightCard.jsx and
src/services/api/freightPayments.js (per the coordinator's correction): `markPaid` sends only
`{paidOn}` -- the real `freight_payments` table has no reference_no column, and
FreightPaymentService.mark_paid() always stamps its own server-side timestamp regardless, so the
client-supplied paidOn is accepted for contract compatibility but not actually used.
"""
from fastapi import APIRouter, Depends

from app.compat.schemas import CamelModel
from app.compat.vendor.common import dec, envelope, iso, paginate_list, vendor_meta
from app.dependencies.vendor import get_current_vendor, get_freight_payment_service
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.payment_service import FreightPaymentService

router = APIRouter(prefix="/freight-payments", tags=["vendor-compat-freight-payments"])

_ALL = PaginationParams(page=1, limit=100000)


def freight_payment_out(row) -> dict:
    return {
        "id": str(row.id),
        "direction": row.direction.value,
        "linkedType": row.linked_type.value,
        "linkedId": str(row.linked_id),
        "transporter": row.transporter,
        "payer": row.payer.value,
        "needsReview": False,  # genuine gap: no such flag is tracked on FreightPayment
        "baseFreight": dec(row.base_freight),
        "gstOnFreight": dec(row.gst_on_freight),
        "gtaForwardCharge": row.gta_forward_charge,
        "tdsAmount": dec(row.tds_amount),
        "netPayableToTransporter": dec(row.net_payable_to_transporter),
        "finalLiabilityAmount": dec(row.final_liability_amount),
        "status": row.status.value,
        "paidOn": iso(row.paid_on),
    }


class MarkPaidRequest(CamelModel):
    paid_on: str | None = None


@router.get("")
def list_freight_payments(
    page: int = 1, limit: int = 20, status: str | None = None, linked_type: str | None = None, linked_id: str | None = None,
    service: FreightPaymentService = Depends(get_freight_payment_service), vendor: Vendor = Depends(get_current_vendor),
):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, status)
    items = [freight_payment_out(r) for r in rows]
    if linked_type:
        items = [i for i in items if i["linkedType"] == linked_type]
    if linked_id:
        items = [i for i in items if i["linkedId"] == linked_id]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/{freight_payment_id}")
def get_freight_payment(freight_payment_id: str, service: FreightPaymentService = Depends(get_freight_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.repo.get_for_vendor(vendor.id, freight_payment_id)
    if not row:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Freight payment not found")
    return envelope(freight_payment_out(row))


@router.patch("/{freight_payment_id}/pay")
def mark_freight_payment_paid(freight_payment_id: str, body: MarkPaidRequest, service: FreightPaymentService = Depends(get_freight_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    service.get_for_vendor(vendor.id, freight_payment_id)  # 404s if not linked back to this vendor
    service.mark_paid(freight_payment_id)
    row = service.repo.get_for_vendor(vendor.id, freight_payment_id)
    return envelope(freight_payment_out(row))
