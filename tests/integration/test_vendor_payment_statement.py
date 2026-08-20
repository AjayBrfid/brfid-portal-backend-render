"""Vendor payment-statement export date-range filtering — was previously a dead pair of
query params (start_date/end_date accepted but ignored, and mismatched in casing against the
frontend's camelCase request) that always exported the vendor's entire payment history."""
import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.procurement import FreightPayer, PurchaseOrder, Quotation, Rfq
from app.models.payment import Payment
from app.models.shipping import Invoice
from tests.integration.helpers import auth_headers, create_sku_variant, create_user, create_vendor, create_warehouse, login


def _create_payment(db, vendor, warehouse, variant, created_at, amount=Decimal("1000.00")):
    rfq = Rfq(ref_code=f"RFQ-{created_at.timestamp():.0f}", warehouse_id=warehouse.id, sku_variant_id=variant.id, quantity=10)
    db.add(rfq)
    db.flush()
    quotation = Quotation(
        rfq_id=rfq.id, vendor_id=vendor.id, unit_price=Decimal("100.00"), total_amount=amount,
        delivery_days=7, validity_days=30, freight_payer=FreightPayer.VENDOR,
    )
    db.add(quotation)
    db.flush()
    po = PurchaseOrder(
        ref_code=f"PO-{created_at.timestamp():.0f}", rfq_id=rfq.id, quotation_id=quotation.id, vendor_id=vendor.id,
        warehouse_id=warehouse.id, sku_variant_id=variant.id, quantity=10, unit_price=Decimal("100.00"),
        grand_total=amount, order_date=created_at.date(), delivery_date=created_at.date() + timedelta(days=7),
    )
    db.add(po)
    db.flush()
    invoice = Invoice(
        po_id=po.id, vendor_id=vendor.id, invoice_number=f"INV-{created_at.timestamp():.0f}",
        invoice_date=created_at.date(), base_amount=amount, gst_amount=Decimal("0"), total_amount=amount,
    )
    db.add(invoice)
    db.flush()
    payment = Payment(invoice_id=invoice.id, po_id=po.id, amount=amount, created_at=created_at)
    db.add(payment)
    db.flush()
    return payment


def _vendor_token(client, db_session, vendor):
    create_user(db_session, "vendor", vendor.id, f"{vendor.code.lower()}@test.com", "vendor-admin")
    db_session.commit()
    return login(client, "vendor", f"{vendor.code.lower()}@test.com")


def test_payment_statement_filters_by_requested_date_range(client, db_session):
    vendor = create_vendor(db_session, code="VEN-PAY-01")
    warehouse = create_warehouse(db_session, code="WH-PAY-01")
    _, variant = create_sku_variant(db_session, style_code="PAY-01", variant_code="SKU-PAY-01")
    db_session.commit()

    in_range = datetime(2026, 8, 5, tzinfo=timezone.utc)
    before_range = datetime(2026, 7, 1, tzinfo=timezone.utc)
    after_range = datetime(2026, 9, 1, tzinfo=timezone.utc)
    _create_payment(db_session, vendor, warehouse, variant, in_range, amount=Decimal("500.00"))
    _create_payment(db_session, vendor, warehouse, variant, before_range, amount=Decimal("600.00"))
    _create_payment(db_session, vendor, warehouse, variant, after_range, amount=Decimal("700.00"))
    db_session.commit()

    token = _vendor_token(client, db_session, vendor)
    resp = client.get(
        "/payments/statement", params={"startDate": "2026-08-01", "endDate": "2026-08-10"}, headers=auth_headers(token),
    )
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.text)))
    amounts = [r[2] for r in rows[1:]]
    assert amounts == ["500.0"]


def test_payment_statement_start_date_only(client, db_session):
    vendor = create_vendor(db_session, code="VEN-PAY-02")
    warehouse = create_warehouse(db_session, code="WH-PAY-02")
    _, variant = create_sku_variant(db_session, style_code="PAY-02", variant_code="SKU-PAY-02")
    db_session.commit()

    _create_payment(db_session, vendor, warehouse, variant, datetime(2026, 8, 5, tzinfo=timezone.utc), amount=Decimal("111.00"))
    _create_payment(db_session, vendor, warehouse, variant, datetime(2026, 7, 1, tzinfo=timezone.utc), amount=Decimal("222.00"))
    db_session.commit()

    token = _vendor_token(client, db_session, vendor)
    resp = client.get("/payments/statement", params={"startDate": "2026-08-01"}, headers=auth_headers(token))
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert [r[2] for r in rows[1:]] == ["111.0"]


def test_payment_statement_end_date_only(client, db_session):
    vendor = create_vendor(db_session, code="VEN-PAY-03")
    warehouse = create_warehouse(db_session, code="WH-PAY-03")
    _, variant = create_sku_variant(db_session, style_code="PAY-03", variant_code="SKU-PAY-03")
    db_session.commit()

    _create_payment(db_session, vendor, warehouse, variant, datetime(2026, 8, 5, tzinfo=timezone.utc), amount=Decimal("111.00"))
    _create_payment(db_session, vendor, warehouse, variant, datetime(2026, 9, 1, tzinfo=timezone.utc), amount=Decimal("222.00"))
    db_session.commit()

    token = _vendor_token(client, db_session, vendor)
    resp = client.get("/payments/statement", params={"endDate": "2026-08-10"}, headers=auth_headers(token))
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert [r[2] for r in rows[1:]] == ["111.0"]


def test_payment_statement_no_dates_returns_full_history(client, db_session):
    vendor = create_vendor(db_session, code="VEN-PAY-04")
    warehouse = create_warehouse(db_session, code="WH-PAY-04")
    _, variant = create_sku_variant(db_session, style_code="PAY-04", variant_code="SKU-PAY-04")
    db_session.commit()

    _create_payment(db_session, vendor, warehouse, variant, datetime(2020, 1, 1, tzinfo=timezone.utc), amount=Decimal("111.00"))
    _create_payment(db_session, vendor, warehouse, variant, datetime(2026, 9, 1, tzinfo=timezone.utc), amount=Decimal("222.00"))
    db_session.commit()

    token = _vendor_token(client, db_session, vendor)
    resp = client.get("/payments/statement", headers=auth_headers(token))
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) - 1 == 2


def test_payment_statement_invalid_date_range_rejected(client, db_session):
    vendor = create_vendor(db_session, code="VEN-PAY-05")
    db_session.commit()
    token = _vendor_token(client, db_session, vendor)

    resp = client.get(
        "/payments/statement", params={"startDate": "2026-08-10", "endDate": "2026-08-01"}, headers=auth_headers(token),
    )
    assert resp.status_code == 400
