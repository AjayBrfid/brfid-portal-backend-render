"""Business-data sections for the Retail dashboard's Export Report (Week/Month) -- see
app/utils/excel_export.py's build_business_report_workbook for how these sections render.
Pure read/query logic, no business-rule side effects."""
import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import PurchaseRequest, TransferOrder
from app.models.retail import StoreInventory, StoreReturn
from app.models.warehouse import Warehouse


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min), datetime.combine(end, time.max)


def build_retail_report_sections(session: Session, store_id: uuid.UUID, start: date, end: date) -> list[dict]:
    start_dt, end_dt = _day_bounds(start, end)

    # Not scoped to the report's period -- shows every transfer order this store has ever
    # received from a warehouse, regardless of status (Pending/Dispatched/Delivered/etc.).
    transfer_rows = session.execute(
        select(TransferOrder, Warehouse, SkuVariant, Sku)
        .join(Warehouse, Warehouse.id == TransferOrder.warehouse_id)
        .outerjoin(SkuVariant, SkuVariant.id == TransferOrder.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .where(TransferOrder.store_id == store_id)
        .order_by(TransferOrder.created_at)
    ).all()
    goods_received_rows = [
        [
            to.ref_code, warehouse.name, variant.variant_code if variant else "-", sku.name if sku else "-", to.quantity, to.status.value,
            to.dispatched_at.strftime("%d %b %Y") if to.dispatched_at else "-",
            to.delivered_at.strftime("%d %b %Y") if to.delivered_at else "-",
        ]
        for to, warehouse, variant, sku in transfer_rows
    ]

    # Not scoped to the report's period like the other sections -- shows every purchase request
    # this store has ever raised, regardless of the selected week/month.
    pr_rows = session.execute(
        select(PurchaseRequest, Warehouse, SkuVariant, Sku)
        .join(Warehouse, Warehouse.id == PurchaseRequest.warehouse_id)
        .outerjoin(SkuVariant, SkuVariant.id == PurchaseRequest.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .where(PurchaseRequest.store_id == store_id)
        .order_by(PurchaseRequest.requested_at)
    ).all()
    purchase_requests_rows = [
        [
            pr.ref_code, warehouse.name, variant.variant_code if variant else "-", sku.name if sku else "-", pr.requested_qty,
            pr.approval_status.value, pr.required_by.strftime("%d %b %Y"),
        ]
        for pr, warehouse, variant, sku in pr_rows
    ]

    return_rows = session.execute(
        select(StoreReturn, Warehouse, SkuVariant, Sku)
        .join(Warehouse, Warehouse.id == StoreReturn.warehouse_id)
        .outerjoin(SkuVariant, SkuVariant.id == StoreReturn.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .where(StoreReturn.store_id == store_id, StoreReturn.requested_at >= start_dt, StoreReturn.requested_at <= end_dt)
        .order_by(StoreReturn.requested_at)
    ).all()
    returns_rows = [
        [
            ret.ref_code, warehouse.name, variant.variant_code if variant else "-", sku.name if sku else "-", ret.qty,
            ret.reason or "-", ret.decision.value, ret.status.value, ret.requested_at.strftime("%d %b %Y"),
        ]
        for ret, warehouse, variant, sku in return_rows
    ]

    inventory_rows = session.execute(
        select(StoreInventory, SkuVariant, Sku)
        .join(SkuVariant, SkuVariant.id == StoreInventory.sku_variant_id)
        .join(Sku, Sku.id == SkuVariant.sku_id)
        .where(StoreInventory.store_id == store_id)
        .order_by(Sku.name)
    ).all()
    pending_stock_rows = [
        [variant.variant_code, sku.name, variant.colour or "-", variant.size or "-", inv.quantity]
        for inv, variant, sku in inventory_rows
    ]

    return [
        {
            "title": "Stock Received from Warehouse", "rows": goods_received_rows,
            "columns": ["Transfer Ref", "Warehouse", "SKU Code", "Product Name", "Quantity", "Status", "Dispatched Date", "Delivered Date"],
        },
        {
            "title": "Purchase Requests Raised", "rows": purchase_requests_rows,
            "columns": ["PR Ref", "Warehouse", "SKU Code", "Product Name", "Requested Qty", "Approval Status", "Required By"],
        },
        {
            "title": "Returns to Warehouse", "rows": returns_rows,
            "columns": ["Return Ref", "Warehouse", "SKU Code", "Product Name", "Qty", "Reason", "Decision", "Status", "Requested Date"],
        },
        {
            "title": "Current Stock", "rows": pending_stock_rows,
            "columns": ["SKU Code", "Product Name", "Colour", "Size", "Quantity"],
        },
    ]
