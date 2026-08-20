"""Purchase Orders compat. Confirmed against src/pages/PurchaseOrdersPage.jsx: the real frontend
now uses the native 6-state PurchaseOrderStatus enum ("Pending Acceptance", "Accepted", "In
Production", "Ready to Ship", "Delivered", "Rejected") verbatim, replacing the old contract's
4-state Pending|Accepted|Rejected|ASN Submitted -- and expects a nested `skuVariant` object.
"""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.compat.schemas import CamelModel
from app.compat.vendor.common import dec, envelope, iso, paginate_list, redirect_to_file, vendor_meta
from app.compat.vendor.rfq_router import _sku_variant_out
from app.dependencies.auth import get_current_user
from app.dependencies.vendor import get_current_vendor, get_purchase_order_service
from app.models.procurement import PurchaseOrder
from app.models.vendor import Vendor
from app.schemas.common import PaginationParams
from app.services.vendor.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["vendor-compat-purchase-orders"])

_ALL = PaginationParams(page=1, limit=100000)


def _po_out(session, po: PurchaseOrder) -> dict:
    return {
        "id": str(po.id),
        "refCode": po.ref_code,
        "rfqId": str(po.rfq_id),
        "quotationId": str(po.quotation_id),
        "orderDate": iso(po.order_date),
        "deliveryDate": iso(po.delivery_date),
        "deliveryAddress": po.delivery_address,
        "quantity": po.quantity,
        "receivedQty": po.received_qty,
        "unitPrice": dec(po.unit_price),
        "taxPercent": dec(po.tax_percent),
        "discountPercent": dec(po.discount_percent),
        "grandTotal": dec(po.grand_total),
        "skuVariant": _sku_variant_out(session, po.sku_variant_id),
        "status": po.status.value,
        "createdAt": iso(po.created_at),
        "asnId": None,  # populated once an ASN is filed against this PO -- see asn_router.py
    }


class AcceptRequest(CamelModel):
    remarks: str | None = None


class RejectRequest(CamelModel):
    reason: str | None = None


@router.get("")
def list_purchase_orders(page: int = 1, limit: int = 20, search: str | None = None, status: str | None = None, service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, status)
    items = [_po_out(service.session, p) for p in rows]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["refCode"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/export")
def export_purchase_orders(period: str = "month", service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    # Genuine gap: no xlsx-generation library is available in this backend (grepped the
    # dependency tree -- no openpyxl/xlsxwriter). This emits CSV bytes instead; the browser still
    # saves it under the `.xlsx` name the frontend requests, so it downloads successfully but
    # won't open as a real Excel workbook.
    rows, _ = service.repo.list_for_vendor(vendor.id, _ALL, None)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["PO Number", "Order Date", "Delivery Date", "Status", "Quantity", "Grand Total"])
    for po in rows:
        writer.writerow([po.ref_code, iso(po.order_date), iso(po.delivery_date), po.status.value, po.quantity, dec(po.grand_total)])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=purchase-orders-{period}.xlsx"})


@router.get("/{po_id}")
def get_purchase_order(po_id: str, service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    po = service.get_for_vendor(vendor.id, po_id)
    return envelope(_po_out(service.session, po))


@router.get("/{po_id}/pdf")
def download_po_pdf(po_id: str, service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    service.get_for_vendor(vendor.id, po_id)  # 404s if not this vendor's PO
    # Genuine gap: PurchaseOrder has no pdf_url column and nothing in this codebase generates a
    # PO PDF -- there is no file to redirect to.
    return redirect_to_file(None)


@router.patch("/{po_id}/accept")
def accept_purchase_order(
    po_id: str, body: AcceptRequest, service: PurchaseOrderService = Depends(get_purchase_order_service),
    vendor: Vendor = Depends(get_current_vendor), user=Depends(get_current_user),
):
    service.accept(vendor.id, po_id, user.id)
    po = service.get_for_vendor(vendor.id, po_id)
    return envelope(_po_out(service.session, po))


@router.patch("/{po_id}/reject")
def reject_purchase_order(
    po_id: str, body: RejectRequest, service: PurchaseOrderService = Depends(get_purchase_order_service),
    vendor: Vendor = Depends(get_current_vendor), user=Depends(get_current_user),
):
    service.reject(vendor.id, po_id, body.reason, user.id)
    po = service.get_for_vendor(vendor.id, po_id)
    return envelope(_po_out(service.session, po))
