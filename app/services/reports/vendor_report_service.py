"""Business-data sections for the Vendor dashboard's Export Report (Week/Month) -- see
app/utils/excel_export.py's build_business_report_workbook for how these sections render.
Pure read/query logic, no business-rule side effects."""
import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Sku, SkuVariant
from app.models.payment import Payment
from app.models.procurement import PurchaseOrder
from app.models.shipping import Asn, AsnItem, Invoice
from app.models.vendor import VendorCatalogSubmission, VendorGood
from app.models.vendor_return import VendorReturn
from app.models.warehouse import Warehouse


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min), datetime.combine(end, time.max)


def build_vendor_report_sections(session: Session, vendor_id: uuid.UUID, start: date, end: date) -> list[dict]:
    start_dt, end_dt = _day_bounds(start, end)

    asn_rows = session.execute(
        select(AsnItem, Asn, SkuVariant, Sku, Warehouse)
        .join(Asn, Asn.id == AsnItem.asn_id)
        .join(PurchaseOrder, PurchaseOrder.id == AsnItem.po_id)
        .outerjoin(SkuVariant, SkuVariant.id == AsnItem.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .outerjoin(Warehouse, Warehouse.id == PurchaseOrder.warehouse_id)
        .where(PurchaseOrder.vendor_id == vendor_id, Asn.created_date >= start_dt, Asn.created_date <= end_dt)
        .order_by(Asn.created_date)
    ).all()
    goods_sent_rows = [
        [
            asn.ref_code, variant.variant_code if variant else "-", sku.name if sku else "-",
            variant.colour if variant else "-", variant.size if variant else "-",
            item.ordered_qty, item.shipped_qty, asn.created_date.strftime("%d %b %Y"),
            warehouse.name if warehouse else "-", warehouse.contact_phone if warehouse else "-",
        ]
        for item, asn, variant, sku, warehouse in asn_rows
    ]

    # Stock Awaiting Receipt mirrors the Vendor's own "My Goods" page exactly (same columns/
    # meaning) -- a live "what's in my own inventory, not yet received into a warehouse" position,
    # not a period transaction log, one row per vendor_goods record. Assigned SKU is resolved the
    # same way the Product Catalog links a submitted good to its approved SKU variant.
    good_rows = session.execute(
        select(VendorGood, SkuVariant)
        .outerjoin(VendorCatalogSubmission, VendorCatalogSubmission.goods_id == VendorGood.id)
        .outerjoin(SkuVariant, SkuVariant.id == VendorCatalogSubmission.sku_variant_id)
        .where(VendorGood.vendor_id == vendor_id)
        .order_by(VendorGood.name)
    ).all()
    stock_awaiting_rows = [
        [
            good.code or str(good.id)[:8], good.name, good.category.value, float(good.quantity),
            good.stock_status.value, variant.variant_code if variant else "-", float(good.price),
        ]
        for good, variant in good_rows
    ]

    invoice_rows = session.execute(
        select(Invoice, PurchaseOrder, Payment)
        .join(PurchaseOrder, PurchaseOrder.id == Invoice.po_id)
        .outerjoin(Payment, Payment.invoice_id == Invoice.id)
        .where(Invoice.vendor_id == vendor_id, Invoice.invoice_date >= start, Invoice.invoice_date <= end)
        .order_by(Invoice.invoice_date)
    ).all()
    payment_status_rows = [
        [
            invoice.invoice_number, po.ref_code, invoice.invoice_date.strftime("%d %b %Y"),
            invoice.due_date.strftime("%d %b %Y") if invoice.due_date else "-",
            float(invoice.total_amount), invoice.status.value,
            payment.status.value if payment else "Not Raised",
            payment.paid_date.strftime("%d %b %Y") if payment and payment.paid_date else "-",
        ]
        for invoice, po, payment in invoice_rows
    ]

    return_rows = session.execute(
        select(VendorReturn, PurchaseOrder, SkuVariant, Sku, Warehouse)
        .join(PurchaseOrder, PurchaseOrder.id == VendorReturn.po_id)
        .outerjoin(SkuVariant, SkuVariant.id == VendorReturn.sku_variant_id)
        .outerjoin(Sku, Sku.id == SkuVariant.sku_id)
        .outerjoin(Warehouse, Warehouse.id == VendorReturn.warehouse_id)
        .where(VendorReturn.vendor_id == vendor_id, VendorReturn.created_at >= start_dt, VendorReturn.created_at <= end_dt)
        .order_by(VendorReturn.created_at)
    ).all()
    returns_rows = [
        [
            po.ref_code, variant.variant_code if variant else "-",
            ret.qty, float(ret.refund_amount) if ret.refund_amount is not None else 0.0,
            ret.status.value, ret.created_at.strftime("%d %b %Y"),
            warehouse.name if warehouse else "-", warehouse.contact_phone if warehouse else "-",
        ]
        for ret, po, variant, sku, warehouse in return_rows
    ]

    return [
        {
            "title": "Goods Sent", "rows": goods_sent_rows,
            "columns": [
                "ASN Ref", "SKU Code", "Product Name", "Colour", "Size", "Ordered Qty", "Shipped Qty", "Dispatch Date",
                "Warehouse Name", "Warehouse Contact",
            ],
        },
        {
            "title": "My Goods Inventory", "rows": stock_awaiting_rows,
            "columns": ["Goods Code", "Product Name", "Category", "Quantity", "Stock Status", "Assigned SKU", "Price/Unit"],
        },
        {
            "title": "Payment Status", "rows": payment_status_rows,
            "columns": ["Invoice No", "PO Ref", "Invoice Date", "Due Date", "Amount", "Invoice Status", "Payment Status", "Paid Date"],
        },
        {
            "title": "Returns from Warehouse", "rows": returns_rows,
            "columns": ["PO Ref", "SKU Code", "Qty", "Refund Amount", "Status", "Created Date", "Warehouse Name", "Warehouse Contact"],
        },
    ]
