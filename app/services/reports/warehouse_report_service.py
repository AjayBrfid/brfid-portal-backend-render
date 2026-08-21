"""Business-data sections for the Warehouse dashboard's Export Report (Week/Month) -- see
app/utils/excel_export.py's build_business_report_workbook for how these sections render.
Pure read/query logic, no business-rule side effects."""
import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import Inventory, TransferOrder
from app.models.procurement import PurchaseOrder
from app.models.retail import Store
from app.models.shipping import Asn, AsnItem, GoodsReceipt
from app.models.vendor import Vendor


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min), datetime.combine(end, time.max)


def build_warehouse_report_sections(session: Session, warehouse_id: uuid.UUID, start: date, end: date) -> list[dict]:
    start_dt, end_dt = _day_bounds(start, end)

    received_rows = session.execute(
        select(AsnItem, Asn, GoodsReceipt, Vendor, SkuVariant, Sku)
        .join(Asn, Asn.id == AsnItem.asn_id)
        .join(GoodsReceipt, GoodsReceipt.asn_id == Asn.id)
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.po_id)
        .join(Vendor, Vendor.id == PurchaseOrder.vendor_id)
        .outerjoin(SkuVariant, SkuVariant.id == AsnItem.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .where(
            PurchaseOrder.warehouse_id == warehouse_id, GoodsReceipt.inspected_at.is_not(None),
            GoodsReceipt.inspected_at >= start_dt, GoodsReceipt.inspected_at <= end_dt,
        )
        .order_by(GoodsReceipt.inspected_at)
    ).all()
    goods_received_rows = [
        [
            asn.ref_code, vendor.name, variant.variant_code if variant else "-", sku.name if sku else "-",
            receipt.received_qty, receipt.accepted_qty, receipt.rejected_qty,
        ]
        for item, asn, receipt, vendor, variant, sku in received_rows
    ]

    transfer_rows = session.execute(
        select(TransferOrder, Store, SkuVariant, Sku)
        .join(Store, Store.id == TransferOrder.store_id)
        .outerjoin(SkuVariant, SkuVariant.id == TransferOrder.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .where(TransferOrder.warehouse_id == warehouse_id, TransferOrder.created_at >= start_dt, TransferOrder.created_at <= end_dt)
        .order_by(TransferOrder.created_at)
    ).all()
    goods_sent_rows = [
        [
            to.ref_code, store.name, variant.variant_code if variant else "-", sku.name if sku else "-", to.quantity, to.status.value,
            to.dispatched_at.strftime("%d %b %Y") if to.dispatched_at else "-",
            to.delivered_at.strftime("%d %b %Y") if to.delivered_at else "-",
        ]
        for to, store, variant, sku in transfer_rows
    ]

    inventory_rows = session.execute(
        select(Inventory, SkuVariant, Sku)
        .join(SkuVariant, SkuVariant.id == Inventory.sku_variant_id)
        .join(Sku, Sku.id == SkuVariant.sku_id)
        .where(Inventory.warehouse_id == warehouse_id)
        .order_by(Sku.name)
    ).all()
    pending_stock_rows = [
        [variant.variant_code, sku.name, variant.colour or "-", variant.size or "-", inv.on_hand, inv.available]
        for inv, variant, sku in inventory_rows
    ]

    return [
        {
            "title": "Goods Received", "rows": goods_received_rows,
            "columns": ["ASN Ref", "Vendor", "SKU Code", "Product Name", "Received Qty", "Accepted Qty", "Rejected Qty"],
        },
        {
            "title": "Goods Sent to Retail", "rows": goods_sent_rows,
            "columns": ["Dispatch Ref", "Store", "SKU Code", "Product Name", "Quantity", "Status", "Dispatched Date", "Delivered Date"],
        },
        {
            "title": "Current Stock", "rows": pending_stock_rows,
            "columns": ["SKU Code", "Product Name", "Colour", "Size", "Total Stock", "Available"],
        },
    ]
