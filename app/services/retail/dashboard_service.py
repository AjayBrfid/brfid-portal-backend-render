import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import PurchaseRequest
from app.models.notification import Notification
from app.models.warehouse import Warehouse, WarehouseStoreLink
from app.schemas.common import PaginationParams
from app.services.retail.product_service import ProductService
from app.services.retail.purchase_request_service import RetailPurchaseRequestService
from app.utils.period import build_buckets, period_start


class RetailDashboardService:
    def __init__(self, session: Session):
        self.session = session
        self.products = ProductService(session)
        self.purchase_requests = RetailPurchaseRequestService(session)

    def _pr_trend(self, store_id: uuid.UUID, period: str) -> dict:
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
        return {"labels": labels, "values": values}

    def _top_requested_skus(self, store_id: uuid.UUID, period: str, limit: int = 5) -> list[dict]:
        start = period_start(period)
        rows = self.session.execute(
            select(
                Sku.name,
                Sku.category,
                func.count().label("order_count"),
                func.coalesce(func.sum(PurchaseRequest.requested_qty), 0).label("units"),
            )
            .select_from(PurchaseRequest)
            .join(SkuVariant, SkuVariant.id == PurchaseRequest.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= start)
            .group_by(Sku.id, Sku.name, Sku.category)
            .order_by(func.count().desc())
            .limit(limit)
        ).all()
        return [{"name": name, "cat": cat, "order_count": int(order_count), "units": int(units)} for name, cat, order_count, units in rows]

    def _employee_alerts(self, user_id: uuid.UUID, limit: int = 5) -> list[dict]:
        rows = self.session.execute(
            select(Notification)
            .where(Notification.recipient_user_id == user_id, Notification.type == "employee-alert", Notification.read.is_(False))
            .order_by(Notification.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [{"id": str(n.id), "title": n.title} for n in rows]

    def get_manager_dashboard(self, store_id: uuid.UUID, user_id: uuid.UUID, sales_period: str, top_sell_period: str) -> dict:
        stock = self.products.get_stock_summary(store_id)
        prs, _ = self.purchase_requests.list_requests(store_id, PaginationParams(page=1, limit=10), search=None, status=None)
        return {
            "total_stock_units": stock["total_units"],
            "category_count": len(stock["by_category"]),
            "low_stock_count": stock["low_stock_count"],
            "pr_trend": self._pr_trend(store_id, sales_period),
            "top_requested_skus": self._top_requested_skus(store_id, top_sell_period),
            "purchase_requests": prs,
            "employee_alerts": self._employee_alerts(user_id),
        }

    def get_admin_dashboard(self, store_id: uuid.UUID, user_id: uuid.UUID, sales_period: str, top_sell_period: str) -> dict:
        base = self.get_manager_dashboard(store_id, user_id, sales_period, top_sell_period)
        del base["employee_alerts"]  # admin dashboard has no staff-alert widget

        stock = self.products.get_stock_summary(store_id)
        month_start = period_start("monthly")

        month_total = self.session.execute(
            select(func.count())
            .select_from(PurchaseRequest)
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= month_start)
        ).scalar_one()

        by_category = self.session.execute(
            select(Sku.category, func.count().label("count"))
            .select_from(PurchaseRequest)
            .join(SkuVariant, SkuVariant.id == PurchaseRequest.sku_variant_id)
            .join(Sku, Sku.id == SkuVariant.sku_id)
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= month_start)
            .group_by(Sku.category)
        ).all()
        cat_labels = [cat or "Uncategorised" for cat, _ in by_category]
        cat_values = [int(count) for _, count in by_category]

        by_warehouse = self.session.execute(
            select(Warehouse.name, func.count().label("count"))
            .select_from(PurchaseRequest)
            .join(Warehouse, Warehouse.id == PurchaseRequest.warehouse_id)
            .where(PurchaseRequest.store_id == store_id, PurchaseRequest.requested_at >= month_start)
            .group_by(Warehouse.id, Warehouse.name)
        ).all()
        total_for_share = sum(int(count) for _, count in by_warehouse) or 1
        prs_by_warehouse = [{"name": name, "share_pct": round(int(count) / total_for_share * 100)} for name, count in by_warehouse]

        base.update({
            "monthly_pr_volume": {"total": int(month_total), "labels": cat_labels, "values": cat_values},
            "prs_by_warehouse": prs_by_warehouse,
            "capacity_used_pct": stock["capacity_used_pct"],
        })
        return base
