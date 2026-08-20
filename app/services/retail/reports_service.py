import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import PurchaseRequest, TransferOrder, TransferOrderStatus
from app.models.retail import StoreDiscount, StoreInventory, StoreReturn, StoreReturnDecision
from app.models.warehouse import Warehouse
from app.services.retail.purchase_request_service import RetailPurchaseRequestService
from app.utils.period import build_buckets, period_start

TOPICS = [
    {"key": "pr", "label": "Purchase Requests"},
    {"key": "shipment", "label": "Shipments"},
    {"key": "stock", "label": "Stock Levels"},
    {"key": "discount", "label": "Discounts"},
    {"key": "replenishment", "label": "Replenishment"},
    {"key": "sales", "label": "Sales"},
    {"key": "profit", "label": "Profit"},
]
_DELIVERED_STATUSES = (TransferOrderStatus.DELIVERED, TransferOrderStatus.COMPLETED)


class RetailReportsService:
    def __init__(self, session: Session):
        self.session = session
        self.purchase_requests = RetailPurchaseRequestService(session)

    def list_topics(self) -> list[dict]:
        return TOPICS

    def get_sales(self, store_id: uuid.UUID, period: str) -> dict:
        # No Sale/SaleLineItem model exists anywhere in this schema - there is no real sales
        # transaction data to report on, only purchase-request/stock activity. Return a
        # well-formed, empty tabular shape rather than fabricating numbers.
        return {"headers": ["Date", "Product", "SKU", "Qty", "Amount"], "rows": []}

    def get_profit(self, store_id: uuid.UUID, period: str) -> dict:
        # Same story as sales - no cost-of-goods/sale-price data backs a real profit figure.
        return {"by_category": []}

    def get_topic_report(self, store_id: uuid.UUID, topic_key: str, period: str) -> dict:
        start = period_start(period)
        if topic_key == "pr":
            rows, _ = self.purchase_requests.list_requests(
                store_id, params=_recent_params(), search=None, status=None
            )
            headers = ["ID", "Date", "Warehouse", "Product", "SKU", "Qty", "Status"]
            return {"headers": headers, "rows": [[r["id"], r["date"], r["warehouse"], r["product"], r["sku"], r["qty"], r["status"]] for r in rows]}

        if topic_key == "shipment":
            result = self.session.execute(
                select(TransferOrder, PurchaseRequest.ref_code, Warehouse.name)
                .join(Warehouse, Warehouse.id == TransferOrder.warehouse_id)
                .outerjoin(PurchaseRequest, PurchaseRequest.id == TransferOrder.pr_id)
                .where(TransferOrder.store_id == store_id, TransferOrder.created_at >= start)
                .order_by(TransferOrder.created_at.desc())
            ).all()
            headers = ["Shipment ID", "PR ID", "Warehouse", "Qty", "Status", "Created"]
            return {
                "headers": headers,
                "rows": [[to.ref_code, pr_ref, wh_name, to.quantity, to.status.value, to.created_at.date().isoformat()] for to, pr_ref, wh_name in result],
            }

        if topic_key == "stock":
            result = self.session.execute(
                select(SkuVariant.variant_code, Sku.name, Sku.category, StoreInventory.quantity)
                .select_from(StoreInventory)
                .join(SkuVariant, SkuVariant.id == StoreInventory.sku_variant_id)
                .join(Sku, Sku.id == SkuVariant.sku_id)
                .where(StoreInventory.store_id == store_id)
            ).all()
            headers = ["SKU", "Product", "Category", "Quantity"]
            return {"headers": headers, "rows": [[sku, name, cat, qty] for sku, name, cat, qty in result]}

        if topic_key == "discount":
            result = self.session.execute(
                select(SkuVariant.variant_code, Sku.name, StoreDiscount.pct)
                .select_from(StoreDiscount)
                .join(SkuVariant, SkuVariant.id == StoreDiscount.sku_variant_id)
                .join(Sku, Sku.id == SkuVariant.sku_id)
                .where(StoreDiscount.store_id == store_id)
            ).all()
            headers = ["SKU", "Product", "Discount %"]
            return {"headers": headers, "rows": [[sku, name, float(pct)] for sku, name, pct in result]}

        if topic_key == "replenishment":
            result = self.session.execute(
                select(SkuVariant.variant_code, StoreReturn.qty, StoreReturn.status, StoreReturn.requested_at)
                .select_from(StoreReturn)
                .join(SkuVariant, SkuVariant.id == StoreReturn.sku_variant_id)
                .where(StoreReturn.store_id == store_id, StoreReturn.decision == StoreReturnDecision.REPLENISH, StoreReturn.requested_at >= start)
                .order_by(StoreReturn.requested_at.desc())
            ).all()
            headers = ["SKU", "Qty", "Status", "Requested"]
            return {"headers": headers, "rows": [[sku, qty, status.value, requested_at.date().isoformat()] for sku, qty, status, requested_at in result]}

        if topic_key == "sales":
            return self.get_sales(store_id, period)

        raise NotFoundException(f"Unknown report topic '{topic_key}'")

    def get_warehouse_relations(self, store_id: uuid.UUID, period: str) -> dict:
        start = period_start(period)

        prs = self.session.execute(
            select(PurchaseRequest, Warehouse.name)
            .join(Warehouse, Warehouse.id == PurchaseRequest.warehouse_id)
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= start)
        ).all()

        total_orders = len(prs)
        by_warehouse_totals: dict[str, dict] = {}
        for pr, warehouse_name in prs:
            entry = by_warehouse_totals.setdefault(warehouse_name, {"total": 0, "fulfilled": 0})
            entry["total"] += 1
            if pr.fulfilment_ref_type is not None:
                entry["fulfilled"] += 1
        by_warehouse = [
            {
                "warehouse": name,
                "total": stats["total"],
                "fulfilled": stats["fulfilled"],
                "fulfilment_rate_pct": round(stats["fulfilled"] / stats["total"] * 100) if stats["total"] else 0,
            }
            for name, stats in by_warehouse_totals.items()
        ]

        buckets = build_buckets(period)
        labels, values = [], []
        for b_start, b_end, label in buckets:
            labels.append(label)
            count = self.session.execute(
                select(func.count())
                .select_from(PurchaseRequest)
                .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= b_start, PurchaseRequest.requested_at < b_end)
            ).scalar_one()
            values.append(int(count))

        avg_order_qty = self.session.execute(
            select(func.coalesce(func.avg(PurchaseRequest.requested_qty), 0))
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= start)
        ).scalar_one()

        most_repeated_row = self.session.execute(
            select(SkuVariant.variant_code, Sku.name, func.count().label("order_count"))
            .select_from(PurchaseRequest)
            .join(SkuVariant, SkuVariant.id == PurchaseRequest.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= start)
            .group_by(SkuVariant.id, SkuVariant.variant_code, Sku.name)
            .order_by(func.count().desc())
            .limit(1)
        ).first()
        most_repeated_sku = (
            {"sku": most_repeated_row[0], "product": most_repeated_row[1], "order_count": int(most_repeated_row[2])}
            if most_repeated_row and most_repeated_row[2] > 1
            else None
        )

        top_fulfilling_warehouse = None
        if by_warehouse:
            top = max(by_warehouse, key=lambda w: w["fulfilment_rate_pct"])
            top_fulfilling_warehouse = {"warehouse": top["warehouse"], "fulfilment_rate_pct": top["fulfilment_rate_pct"]}

        return {
            "total_orders": total_orders,
            "by_warehouse": by_warehouse,
            "labels": labels,
            "values": values,
            "avg_order_qty": round(float(avg_order_qty), 1),
            "most_repeated_sku": most_repeated_sku,
            "top_fulfilling_warehouse": top_fulfilling_warehouse,
        }


def _recent_params():
    from app.schemas.common import PaginationParams

    return PaginationParams(page=1, limit=50)
