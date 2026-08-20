"""RFQ -> quotation -> PO -> ASN -> goods-receipt inspection chain, including the auto-created
VendorReturn for rejected units and auto-created Payment on invoice acceptance — the same flow
verified manually during Phase 4.
"""
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


def _setup(db_session):
    warehouse = create_warehouse(db_session, code="WH-VP-01")
    store = create_store(db_session, code="STR-VP-01")
    vendor = create_vendor(db_session, code="VEN-VP-01")
    link_warehouse_store(db_session, warehouse, store)
    sku, variant = create_sku_variant(db_session, "SKU-VP-01", "SKU-VP-01-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor)
    create_user(db_session, "warehouse", warehouse.id, "wh-vp@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-vp@test.com", "store-admin")
    create_user(db_session, "vendor", vendor.id, "vendor-vp@test.com", "vendor-admin")
    db_session.commit()
    return warehouse, store, vendor, variant


def test_full_procurement_chain_with_partial_rejection(client, db_session):
    warehouse, store, vendor, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-vp@test.com")
    store_token = login(client, "store", "store-vp@test.com")
    vendor_token = login(client, "vendor", "vendor-vp@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 50, "expected_date": "2026-09-15"},
    )
    pr_ref = pr_resp.json()["data"]["id"]

    rfq_resp = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor.id)]},
    )
    assert rfq_resp.status_code == 200, rfq_resp.text
    rfq_id = rfq_resp.json()["data"]["id"]

    vendor_rfqs = client.get("/api/v1/vendor/rfqs", headers=auth_headers(vendor_token))
    assert vendor_rfqs.json()["meta"]["totalItems"] == 1

    quote_resp = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={"unit_price": 150, "tax_percent": 5, "discount_percent": 0, "delivery_days": 7, "validity_days": 30, "freight_payer": "vendor"},
    )
    assert quote_resp.status_code == 201, quote_resp.text
    quote = quote_resp.json()["data"]
    assert quote["total_amount"] == 7875.0  # 150 * 50 * 1.05
    quote_id = quote["id"]

    select_resp = client.post(f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token), json={"quotation_id": quote_id})
    assert select_resp.status_code == 200
    po_id = select_resp.json()["data"]["po_id"]

    accept_resp = client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_token))
    assert accept_resp.json()["data"]["status"] == "Accepted"

    asn_resp = client.post(f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_token), json={"shipped_qty": 50})
    assert asn_resp.status_code == 201, asn_resp.text
    asn_id = asn_resp.json()["data"]["id"]
    client.put(f"/api/v1/vendor/asn/{asn_id}/submit", headers=auth_headers(vendor_token))

    inspect_resp = client.post(
        f"/api/v1/warehouse/purchase-orders/{po_id}/asns/{asn_id}/inspect", headers=auth_headers(wh_token),
        json={"accepted_qty": 45, "rejected_qty": 5, "rejection_reason": "Stitching defects"},
    )
    assert inspect_resp.status_code == 200, inspect_resp.text
    assert inspect_resp.json()["data"]["inspection_status"] == "partial"

    # Accepted units landed in warehouse on_hand; rejected units auto-created a VendorReturn.
    inv_resp = client.get("/api/v1/warehouse/inventory", headers=auth_headers(wh_token))
    assert inv_resp.json()["data"][0]["on_hand"] == 45

    returns_resp = client.get("/api/v1/warehouse/returns/vendor", headers=auth_headers(wh_token))
    returns = returns_resp.json()["data"]
    assert len(returns) == 1
    assert returns[0]["qty"] == 5
    assert returns[0]["status"] == "Initiated"

    approve_return_resp = client.post(f"/api/v1/warehouse/returns/vendor/{returns[0]['id']}/approve", headers=auth_headers(wh_token), json={})
    assert approve_return_resp.json()["data"]["status"] == "Approved"

    invoice_resp = client.post(
        "/api/v1/vendor/invoices", headers=auth_headers(vendor_token),
        json={"po_id": po_id, "invoice_number": "INV-VP-001", "invoice_date": "2026-08-13", "base_amount": 6750, "gst_amount": 337.5},
    )
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice_id = invoice_resp.json()["data"]["id"]
    assert invoice_resp.json()["data"]["total_amount"] == 7087.5

    accept_invoice_resp = client.patch(f"/api/v1/warehouse/invoices/{invoice_id}/status", headers=auth_headers(wh_token), json={"status": "accepted"})
    assert accept_invoice_resp.json()["data"]["status"] == "accepted"

    payment_summary = client.get("/api/v1/vendor/payments/summary", headers=auth_headers(vendor_token))
    assert payment_summary.json()["data"]["Pending"]["amount"] == 7087.5


def test_eligible_vendors_lookup_accepts_the_sku_code_the_frontend_actually_sends(client, db_session):
    """WhPrIncoming.jsx calls GET /rfqs/eligible-vendors/{sku} with the human-readable variant
    code (e.g. "SKU-VP-01-BLK-M"), not the variant's UUID — this must resolve correctly instead
    of crashing with a Postgres "invalid input syntax for type uuid" error."""
    warehouse, store, vendor, variant = _setup(db_session)
    link_warehouse_vendor(db_session, warehouse, vendor)
    db_session.commit()
    wh_token = login(client, "warehouse", "wh-vp@test.com")

    resp = client.get(f"/api/v1/warehouse/rfqs/eligible-vendors/{variant.variant_code}", headers=auth_headers(wh_token))
    assert resp.status_code == 200, resp.text
    vendors = resp.json()["data"]
    assert len(vendors) == 1
    assert vendors[0]["id"] == str(vendor.id)
    assert vendors[0]["eligible"] is True


def test_eligible_vendors_lookup_unknown_sku_returns_404(client, db_session):
    warehouse, store, vendor, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-vp@test.com")

    resp = client.get("/api/v1/warehouse/rfqs/eligible-vendors/NOT-A-REAL-SKU", headers=auth_headers(wh_token))
    assert resp.status_code == 404


def test_rfq_list_and_detail_include_pr_and_store(client, db_session):
    """WhRfqList.jsx (both the table and its eye-button dialog) and WhRfqDetail.jsx all read
    pr_ref/store/qty/required_by/quotation_count/po_id off this same dict — none of them were
    ever populated, so PR ID and Store showed up blank everywhere."""
    warehouse, store, vendor, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-vp@test.com")
    store_token = login(client, "store", "store-vp@test.com")

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

    list_resp = client.get("/api/v1/warehouse/rfqs", headers=auth_headers(wh_token))
    assert list_resp.status_code == 200
    row = next(r for r in list_resp.json()["data"] if r["id"] == rfq_id)
    assert row["pr_ref"] == pr_ref
    assert row["store"] == store.name
    assert row["warehouse"] == warehouse.name
    assert row["qty"] == 20
    assert row["quotation_count"] == 0
    assert row["po_id"] is None
    assert row["selected_vendor_id"] is None

    detail_resp = client.get(f"/api/v1/warehouse/rfqs/{rfq_id}", headers=auth_headers(wh_token))
    detail = detail_resp.json()["data"]
    assert detail["pr_ref"] == pr_ref
    assert detail["store"] == store.name
    assert detail["qty"] == 20
    assert detail["required_by"] is not None


def test_vendor_cannot_accept_already_accepted_po(client, db_session):
    warehouse, store, vendor, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-vp@test.com")
    store_token = login(client, "store", "store-vp@test.com")
    vendor_token = login(client, "vendor", "vendor-vp@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 10, "expected_date": "2026-09-15"},
    )
    pr_ref = pr_resp.json()["data"]["id"]
    rfq_id = client.post(f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token), json={"invited_vendor_ids": [str(vendor.id)]}).json()["data"]["id"]
    quote_id = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={"unit_price": 100, "tax_percent": 0, "discount_percent": 0, "delivery_days": 5, "validity_days": 30, "freight_payer": "vendor"},
    ).json()["data"]["id"]
    po_id = client.post(f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token), json={"quotation_id": quote_id}).json()["data"]["po_id"]

    first_accept = client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_token))
    assert first_accept.status_code == 200

    second_accept = client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_token))
    assert second_accept.status_code == 409
    assert second_accept.json()["error"]["code"] == "CONFLICT"
