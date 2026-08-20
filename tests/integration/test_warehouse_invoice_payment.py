"""WMS invoice module redesign: the vendor's ASN submission (compat CreateAsnPage.jsx contract)
accepts discount_amount/freight_amount on its invoice sub-object so total_amount reflects all
four figures; "Mark as Paid" previously called a POST /purchase-orders/:id/asns/:id/invoice/pay
route that never existed (and even if it had, the frontend's ASN-matching lookup by
invoice_number could never find a match, since AsnService._to_out() never included an `invoice`
key) - it's replaced by PATCH /invoices/:id/pay, keyed directly by the invoice's own id; and the
dashboard's "Pending Vendor Payments" stat previously summed Payment rows that only ever got
created once an invoice was explicitly "accepted" (a transition nothing in this UI ever
triggered), so it was always 0 regardless of how many unpaid invoices existed.

Invoices are created by the VENDOR submitting an ASN (the warehouse's own "Log ASN" endpoint was
removed — a warehouse only ever inspects what the vendor already submitted), so these tests go
through the vendor's compat ASN-submission contract (multipart `payload` JSON, mounted at root —
see app/compat/vendor/asn_router.py) rather than a warehouse-side creation call.
"""
import json

from tests.integration.helpers import (
    auth_headers,
    create_sku_variant,
    create_store,
    create_user,
    create_vendor,
    create_warehouse,
    link_sku_supplying_vendor,
    link_warehouse_store,
    link_warehouse_vendor,
    login,
)


def _create_accepted_po(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-INV-01")
    store = create_store(db_session, code="STR-INV-01")
    vendor = create_vendor(db_session, code="VEN-INV-01")
    link_warehouse_store(db_session, warehouse, store)
    link_warehouse_vendor(db_session, warehouse, vendor)
    sku, variant = create_sku_variant(db_session, "SKU-INV-01", "SKU-INV-01-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor)
    create_user(db_session, "warehouse", warehouse.id, "wh-inv@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-inv@test.com", "store-admin")
    create_user(db_session, "vendor", vendor.id, "vendor-inv@test.com", "vendor-admin")
    db_session.commit()

    wh_token = login(client, "warehouse", "wh-inv@test.com")
    store_token = login(client, "store", "store-inv@test.com")
    vendor_token = login(client, "vendor", "vendor-inv@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 20, "expected_date": "2026-09-15"},
    )
    pr_ref = pr_resp.json()["data"]["id"]
    rfq_resp = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor.id)]},
    )
    rfq_id = rfq_resp.json()["data"]["id"]
    quote_resp = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={"unit_price": 100, "tax_percent": 10, "discount_percent": 0, "delivery_days": 7, "validity_days": 30, "freight_payer": "vendor"},
    )
    quote_id = quote_resp.json()["data"]["id"]
    select_resp = client.post(f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token), json={"quotation_id": quote_id})
    po_id = select_resp.json()["data"]["po_id"]
    client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_token))
    return warehouse, po_id, wh_token, vendor_token


def _submit_asn(client, po_id, vendor_token, *, discount_amount=0, freight_amount=0, invoice_number):
    payload = {
        "shippedQty": 20,
        "expectedDeliveryDate": "2026-09-10",
        "draftStatus": "Submitted",
        "shipment": {"dispatchDate": "2026-09-01", "transporter": "BlueDart", "vehicleNo": "MH01AB1234"},
        "freight": {"payer": "vendor"},
        "invoice": {
            "invoiceNumber": invoice_number, "invoiceDate": "2026-09-01",
            "discountAmount": discount_amount, "freightAmount": freight_amount,
        },
    }
    return client.post(f"/purchase-orders/{po_id}/asn", headers=auth_headers(vendor_token), data={"payload": json.dumps(payload)})


def test_log_asn_invoice_includes_discount_and_freight_in_total(client, db_session):
    warehouse, po_id, wh_token, vendor_token = _create_accepted_po(client, db_session)

    log_resp = _submit_asn(client, po_id, vendor_token, discount_amount=50, freight_amount=100, invoice_number="INV-DF-001")
    assert log_resp.status_code == 201, log_resp.text

    invoices = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}/invoices", headers=auth_headers(wh_token))
    invoice = invoices.json()["data"][0]
    # base = 20 * 100 = 2000, gst = 200, total = 2000 + 200 + 100(freight) - 50(discount) = 2250
    assert invoice["base_amount"] == 2000.0
    assert invoice["gst_amount"] == 200.0
    assert invoice["discount_amount"] == 50.0
    assert invoice["freight_amount"] == 100.0
    assert invoice["total_amount"] == 2250.0
    assert invoice["paid"] is False


def test_mark_invoice_paid_updates_status_and_dashboard_stat(client, db_session):
    warehouse, po_id, wh_token, vendor_token = _create_accepted_po(client, db_session)

    log_resp = _submit_asn(client, po_id, vendor_token, invoice_number="INV-DF-002")
    assert log_resp.status_code == 201, log_resp.text
    invoices = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}/invoices", headers=auth_headers(wh_token)).json()["data"]
    invoice = invoices[0]
    invoice_id = invoice["id"]

    summary_before = client.get("/api/v1/warehouse/dashboard/summary", headers=auth_headers(wh_token)).json()["data"]
    assert summary_before["pending_vendor_payments_inr"] == invoice["total_amount"]

    pay_resp = client.patch(f"/api/v1/warehouse/invoices/{invoice_id}/pay", headers=auth_headers(wh_token))
    assert pay_resp.status_code == 200, pay_resp.text
    assert pay_resp.json()["data"]["paid"] is True

    summary_after = client.get("/api/v1/warehouse/dashboard/summary", headers=auth_headers(wh_token)).json()["data"]
    assert summary_after["pending_vendor_payments_inr"] == 0.0

    again = client.patch(f"/api/v1/warehouse/invoices/{invoice_id}/pay", headers=auth_headers(wh_token))
    assert again.status_code == 409
