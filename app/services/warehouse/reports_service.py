import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import FulfilmentType, PurchaseRequest, PurchaseRequestApprovalStatus
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus
from app.models.vendor import Vendor
from app.models.warehouse import WarehouseVendorLink
from app.utils.period import build_buckets, period_start

_OPEN_PO_STATUSES = (
    PurchaseOrderStatus.PENDING_ACCEPTANCE,
    PurchaseOrderStatus.ACCEPTED,
    PurchaseOrderStatus.IN_PRODUCTION,
    PurchaseOrderStatus.READY_TO_SHIP,
)
# Slice label -> color, since the frontend's ReportDonut has no client-side palette for this
# chart (unlike retail's warehouse-relations donut) - the backend must supply the color itself.
_BREAKDOWN_COLORS = {
    "Fulfilled from Stock": "#34ACE0",
    "Fulfilled via RFQ": "#1C7FAD",
    "Pending": "#F5A524",
    "Declined": "#EF4444",
}


class WarehouseReportsService:
    def __init__(self, session: Session):
        self.session = session

    def get_summary(self, warehouse_id: uuid.UUID, period: str) -> dict:
        start = period_start(period)

        total_requests, fulfilled, pending = self.session.execute(
            select(
                func.count(),
                func.count().filter(PurchaseRequest.fulfilment_ref_type.is_not(None)),
                func.count().filter(
                    PurchaseRequest.fulfilment_ref_type.is_(None),
                    PurchaseRequest.approval_status != PurchaseRequestApprovalStatus.DECLINED,
                ),
            )
            .select_from(PurchaseRequest)
            .where(PurchaseRequest.warehouse_id == warehouse_id, PurchaseRequest.requested_at >= start)
        ).one()

        po_fulfilled, po_undelivered = self.session.execute(
            select(
                func.count().filter(PurchaseOrder.status == PurchaseOrderStatus.DELIVERED),
                func.count().filter(PurchaseOrder.status != PurchaseOrderStatus.DELIVERED),
            )
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.warehouse_id == warehouse_id, PurchaseOrder.order_date >= start.date())
        ).one()

        return {
            "total_requests": int(total_requests),
            "fulfilled": int(fulfilled),
            "pending": int(pending),
            "po_undelivered": int(po_undelivered),
            "po_fulfilled": int(po_fulfilled),
        }

    def get_trend(self, warehouse_id: uuid.UUID, period: str) -> dict:
        buckets = build_buckets(period)
        labels, requests, fulfilled = [], [], []
        for b_start, b_end, label in buckets:
            labels.append(label)
            r, f = self.session.execute(
                select(func.count(), func.count().filter(PurchaseRequest.fulfilment_ref_type.is_not(None)))
                .select_from(PurchaseRequest)
                .where(PurchaseRequest.warehouse_id == warehouse_id, PurchaseRequest.requested_at >= b_start, PurchaseRequest.requested_at < b_end)
            ).one()
            requests.append(int(r))
            fulfilled.append(int(f))
        return {"labels": labels, "requests": requests, "fulfilled": fulfilled}

    def get_fulfilment_breakdown(self, warehouse_id: uuid.UUID, period: str) -> list[dict]:
        start = period_start(period)
        stock, rfq, pending, declined = self.session.execute(
            select(
                func.count().filter(PurchaseRequest.fulfilment_type == FulfilmentType.STOCK),
                func.count().filter(PurchaseRequest.fulfilment_type.in_((FulfilmentType.RFQ, FulfilmentType.SPLIT))),
                func.count().filter(
                    PurchaseRequest.fulfilment_ref_type.is_(None),
                    PurchaseRequest.approval_status != PurchaseRequestApprovalStatus.DECLINED,
                ),
                func.count().filter(PurchaseRequest.approval_status == PurchaseRequestApprovalStatus.DECLINED),
            )
            .select_from(PurchaseRequest)
            .where(PurchaseRequest.warehouse_id == warehouse_id, PurchaseRequest.requested_at >= start)
        ).one()

        slices = [
            ("Fulfilled from Stock", stock),
            ("Fulfilled via RFQ", rfq),
            ("Pending", pending),
            ("Declined", declined),
        ]
        return [{"label": label, "value": int(value), "color": _BREAKDOWN_COLORS[label]} for label, value in slices if value > 0]

    def get_top_requested_skus(self, warehouse_id: uuid.UUID, period: str, limit: int) -> list[list]:
        start = period_start(period)
        rows = self.session.execute(
            select(SkuVariant.variant_code, func.coalesce(func.sum(PurchaseRequest.requested_qty), 0).label("qty"))
            .select_from(PurchaseRequest)
            .join(SkuVariant, SkuVariant.id == PurchaseRequest.sku_variant_id)
            .where(PurchaseRequest.warehouse_id == warehouse_id, PurchaseRequest.requested_at >= start)
            .group_by(SkuVariant.variant_code)
            .order_by(func.sum(PurchaseRequest.requested_qty).desc())
            .limit(limit)
        ).all()
        return [[sku, int(qty)] for sku, qty in rows]

    def get_vendor_po_status(self, warehouse_id: uuid.UUID, period: str) -> list[dict]:
        start = period_start(period)
        rows = self.session.execute(
            select(
                Vendor.name,
                func.count().filter(PurchaseOrder.status == PurchaseOrderStatus.DELIVERED).label("delivered"),
                func.count().filter(PurchaseOrder.status != PurchaseOrderStatus.DELIVERED).label("undelivered"),
            )
            .select_from(WarehouseVendorLink)
            .join(Vendor, Vendor.id == WarehouseVendorLink.vendor_id)
            .outerjoin(
                PurchaseOrder,
                (PurchaseOrder.vendor_id == Vendor.id)
                & (PurchaseOrder.warehouse_id == warehouse_id)
                & (PurchaseOrder.order_date >= start.date()),
            )
            .where(WarehouseVendorLink.warehouse_id == warehouse_id)
            .group_by(Vendor.id, Vendor.name)
        ).all()
        return [{"name": name, "delivered": int(delivered), "undelivered": int(undelivered)} for name, delivered, undelivered in rows]
