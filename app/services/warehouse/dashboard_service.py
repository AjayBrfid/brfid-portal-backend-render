import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import (
    Inventory,
    PurchaseRequest,
    PurchaseRequestApprovalStatus,
    TransferOrder,
    TransferOrderStatus,
)
from app.models.payment import Payment, PaymentStatus
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus, Rfq, RfqStatus
from app.models.shipping import Asn, AsnItem, GoodsReceipt, Invoice, InvoiceStatus
from app.utils.period import build_buckets, period_start

_OPEN_PO_STATUSES = (
    PurchaseOrderStatus.PENDING_ACCEPTANCE,
    PurchaseOrderStatus.ACCEPTED,
    PurchaseOrderStatus.IN_PRODUCTION,
    PurchaseOrderStatus.READY_TO_SHIP,
)
# Mirrors the vendor dashboard's _QUOTABLE_RFQ_STATUSES, plus READY_FOR_COMPARISON - all states
# where the warehouse itself still has an RFQ open/unresolved.
_OPEN_RFQ_STATUSES = (
    RfqStatus.SENT,
    RfqStatus.AWAITING_QUOTATIONS,
    RfqStatus.PARTIALLY_RESPONDED,
    RfqStatus.READY_FOR_COMPARISON,
)
_DISPATCHED_TO_STORE_STATUSES = (TransferOrderStatus.DISPATCHED, TransferOrderStatus.DELIVERED, TransferOrderStatus.COMPLETED)


class WarehouseDashboardService:
    def __init__(self, session: Session):
        self.session = session

    def get_summary(self, warehouse_id: uuid.UUID) -> dict:
        total_goods_on_hand = self.session.execute(
            select(func.coalesce(func.sum(Inventory.on_hand), 0)).where(Inventory.warehouse_id == warehouse_id)
        ).scalar_one()

        start = period_start("monthly")
        goods_received_this_period = self.session.execute(
            select(func.coalesce(func.sum(GoodsReceipt.accepted_qty), 0))
            .join(Asn, Asn.id == GoodsReceipt.asn_id)
            .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
            .where(PurchaseOrder.warehouse_id == warehouse_id, GoodsReceipt.inspected_at.is_not(None), GoodsReceipt.inspected_at >= start)
        ).scalar_one()

        open_pos = self.session.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.warehouse_id == warehouse_id, PurchaseOrder.status.in_(_OPEN_PO_STATUSES))
        ).scalar_one()

        pending_retailer_orders = self.session.execute(
            select(func.count())
            .select_from(PurchaseRequest)
            .where(
                PurchaseRequest.warehouse_id == warehouse_id,
                PurchaseRequest.fulfilment_ref_type.is_(None),
                PurchaseRequest.approval_status != PurchaseRequestApprovalStatus.DECLINED,
            )
        ).scalar_one()

        # An Invoice only gets a Payment row once someone explicitly "accepts" it — before that
        # (or if it's never been actioned at all) it's still money owed to the vendor, so this
        # counts every received-but-unpaid Invoice directly rather than only ones that already
        # went through that transition (which, until "Mark as Paid" worked, was effectively none).
        pending_vendor_payments_inr = self.session.execute(
            select(func.coalesce(func.sum(Invoice.total_amount), 0))
            .join(PurchaseOrder, PurchaseOrder.id == Invoice.po_id)
            .outerjoin(Payment, Payment.invoice_id == Invoice.id)
            .where(
                PurchaseOrder.warehouse_id == warehouse_id,
                Invoice.status != InvoiceStatus.REJECTED,
                (Payment.id.is_(None)) | (Payment.status != PaymentStatus.PAID),
            )
        ).scalar_one()

        pending_rfqs = self.session.execute(
            select(func.count()).select_from(Rfq).where(Rfq.warehouse_id == warehouse_id, Rfq.status.in_(_OPEN_RFQ_STATUSES))
        ).scalar_one()

        return {
            "total_goods_on_hand": int(total_goods_on_hand),
            "goods_received_this_period": int(goods_received_this_period),
            "open_pos": int(open_pos),
            "pending_retailer_orders": int(pending_retailer_orders),
            "pending_vendor_payments_inr": float(pending_vendor_payments_inr),
            "pending_rfqs": int(pending_rfqs),
        }

    def get_goods_flow(self, warehouse_id: uuid.UUID, period: str) -> dict:
        buckets = build_buckets(period)
        labels, received, fulfilled = [], [], []
        for b_start, b_end, label in buckets:
            labels.append(label)
            r = self.session.execute(
                select(func.coalesce(func.sum(GoodsReceipt.accepted_qty), 0))
                .join(Asn, Asn.id == GoodsReceipt.asn_id)
                .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
                .where(
                    PurchaseOrder.warehouse_id == warehouse_id,
                    GoodsReceipt.inspected_at.is_not(None),
                    GoodsReceipt.inspected_at >= b_start,
                    GoodsReceipt.inspected_at < b_end,
                )
            ).scalar_one()
            f = self.session.execute(
                select(func.coalesce(func.sum(TransferOrder.quantity), 0)).where(
                    TransferOrder.warehouse_id == warehouse_id,
                    TransferOrder.status.in_(_DISPATCHED_TO_STORE_STATUSES),
                    TransferOrder.created_at >= b_start,
                    TransferOrder.created_at < b_end,
                )
            ).scalar_one()
            received.append(int(r))
            fulfilled.append(int(f))
        return {"labels": labels, "received": received, "fulfilled": fulfilled}

    def get_top_skus(self, warehouse_id: uuid.UUID, period: str, limit: int) -> list[dict]:
        start = period_start(period)

        # GoodsReceipt.accepted_qty is per-ASN (not per SKU line - see the model's docstring),
        # so per-SKU "received" is approximated from AsnItem.shipped_qty, the finest-grained
        # per-line quantity actually available.
        received_rows = self.session.execute(
            select(SkuVariant.id, func.coalesce(func.sum(AsnItem.shipped_qty), 0).label("qty"))
            .select_from(AsnItem)
            .join(PurchaseOrder, PurchaseOrder.id == AsnItem.po_id)
            .join(SkuVariant, SkuVariant.id == AsnItem.sku_variant_id)
            .where(PurchaseOrder.warehouse_id == warehouse_id, AsnItem.created_at >= start)
            .group_by(SkuVariant.id)
        ).all()
        received_by_variant = {variant_id: int(qty) for variant_id, qty in received_rows}

        dispatched_rows = self.session.execute(
            select(TransferOrder.sku_variant_id, func.coalesce(func.sum(TransferOrder.quantity), 0).label("qty"))
            .where(
                TransferOrder.warehouse_id == warehouse_id,
                TransferOrder.status.in_(_DISPATCHED_TO_STORE_STATUSES),
                TransferOrder.created_at >= start,
            )
            .group_by(TransferOrder.sku_variant_id)
        ).all()
        dispatched_by_variant = {variant_id: int(qty) for variant_id, qty in dispatched_rows}

        variant_ids = set(received_by_variant) | set(dispatched_by_variant)
        if not variant_ids:
            return []

        variants = self.session.execute(
            select(SkuVariant.id, SkuVariant.variant_code, Sku.name)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(SkuVariant.id.in_(variant_ids))
        ).all()

        rows = [
            {
                "sku": variant_code,
                "name": name,
                "received": received_by_variant.get(variant_id, 0),
                "dispatched_to_retail": dispatched_by_variant.get(variant_id, 0),
            }
            for variant_id, variant_code, name in variants
        ]
        rows.sort(key=lambda r: r["received"] + r["dispatched_to_retail"], reverse=True)
        return rows[:limit]
