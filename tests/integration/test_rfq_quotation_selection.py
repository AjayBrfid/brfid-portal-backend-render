"""Warehouse-side quotation comparison + vendor selection on the Full RFQ screen
(WhRfqDetail.jsx): quotations must carry vendor_name/tax_percent/discount_percent/
lead_time_days/valid_until/submitted_at (previously missing/misnamed), select-vendor must
accept a quotation_id (previously the frontend sent vendor_id, which the schema rejects), and
RFQ status must only become Partially Responded while fewer vendors have quoted than were
invited -- Ready for Comparison once all of them have.
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


def _submit(client, vendor_token, rfq_id, unit_price=100):
    return client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={"unit_price": unit_price, "tax_percent": 5, "discount_percent": 0, "delivery_days": 10, "validity_days": 30, "freight_payer": "vendor"},
    )


def test_quotation_fields_and_status_transitions_and_vendor_selection(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-RQ-01")
    store = create_store(db_session, code="STR-RQ-01")
    vendor_a = create_vendor(db_session, code="VEN-RQ-01")
    vendor_b = create_vendor(db_session, code="VEN-RQ-02")
    link_warehouse_store(db_session, warehouse, store)
    sku, variant = create_sku_variant(db_session, "SKU-RQ-01", "SKU-RQ-01-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor_a)
    link_sku_supplying_vendor(db_session, variant, vendor_b)
    link_warehouse_vendor(db_session, warehouse, vendor_a)
    link_warehouse_vendor(db_session, warehouse, vendor_b)
    create_user(db_session, "warehouse", warehouse.id, "wh-rq@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-rq@test.com", "store-admin")
    create_user(db_session, "vendor", vendor_a.id, "vendor-rq-a@test.com", "vendor-admin")
    create_user(db_session, "vendor", vendor_b.id, "vendor-rq-b@test.com", "vendor-admin")
    db_session.commit()

    wh_token = login(client, "warehouse", "wh-rq@test.com")
    store_token = login(client, "store", "store-rq@test.com")
    vendor_a_token = login(client, "vendor", "vendor-rq-a@test.com")
    vendor_b_token = login(client, "vendor", "vendor-rq-b@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 20, "expected_date": "2026-09-20"},
    )
    pr_ref = pr_resp.json()["data"]["id"]
    rfq_resp = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor_a.id), str(vendor_b.id)]},
    )
    rfq_id = rfq_resp.json()["data"]["id"]

    # Only one of two invited vendors has responded so far -> Partially Responded, not
    # Ready for Comparison (the bug: it used to jump straight to Partially Responded
    # unconditionally on ANY submission, which is what this case is actually testing for).
    submit_a = _submit(client, vendor_a_token, rfq_id, unit_price=100)
    assert submit_a.status_code == 201, submit_a.text
    rfq_after_one = client.get(f"/api/v1/warehouse/rfqs/{rfq_id}", headers=auth_headers(wh_token)).json()["data"]
    assert rfq_after_one["status"] == "Partially Responded"

    # Quotations list must carry every field the Full RFQ screen renders.
    quotes_resp = client.get(f"/api/v1/warehouse/rfqs/{rfq_id}/quotations", headers=auth_headers(wh_token))
    assert quotes_resp.status_code == 200
    q = quotes_resp.json()["data"][0]
    assert q["vendor_name"] == vendor_a.name
    assert q["tax_percent"] == 5.0
    assert q["discount_percent"] == 0.0
    assert q["lead_time_days"] == 10
    assert q["valid_until"] is not None
    assert q["submitted_at"] is not None
    quotation_id = q["id"]

    # Second (and last) invited vendor now responds -> every invited vendor has quoted ->
    # Ready for Comparison.
    submit_b = _submit(client, vendor_b_token, rfq_id, unit_price=90)
    assert submit_b.status_code == 201, submit_b.text
    rfq_after_both = client.get(f"/api/v1/warehouse/rfqs/{rfq_id}", headers=auth_headers(wh_token)).json()["data"]
    assert rfq_after_both["status"] == "Ready for Comparison"

    # Selecting a vendor is keyed by quotation_id, not vendor_id (the frontend used to send
    # vendor_id, which this endpoint's schema has always rejected).
    select_resp = client.post(
        f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token),
        json={"quotation_id": quotation_id},
    )
    assert select_resp.status_code == 200, select_resp.text
    assert select_resp.json()["data"]["vendor_name"] == vendor_a.name
    assert select_resp.json()["data"]["po_id"]
