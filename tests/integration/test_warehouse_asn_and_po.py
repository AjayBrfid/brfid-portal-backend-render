"""Vendor-initiated ASN creation/inspection (the warehouse's own "Log ASN" endpoint was removed —
a vendor may submit exactly one ASN per PO, which locks until the warehouse partially/fully
rejects it, at which point the vendor corrects and resubmits the SAME ASN rather than filing an
unrelated second one), the ASN inspection dialog (which could never find a pending ASN because
the response was missing the one field — status — the frontend actually checks), plus the
"Raise PO" screen's purchase-order detail fields (several were entirely absent from the
response: qty, vendor_name, warehouse, tax_percent, discount_percent, delivery_address, rfq_ref).
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
    warehouse = create_warehouse(db_session, code="WH-AP-01")
    store = create_store(db_session, code="STR-AP-01")
    vendor = create_vendor(db_session, code="VEN-AP-01")
    link_warehouse_store(db_session, warehouse, store)
    link_warehouse_vendor(db_session, warehouse, vendor)
    sku, variant = create_sku_variant(db_session, "SKU-AP-01", "SKU-AP-01-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor)
    create_user(db_session, "warehouse", warehouse.id, "wh-ap@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-ap@test.com", "store-admin")
    create_user(db_session, "vendor", vendor.id, "vendor-ap@test.com", "vendor-admin")
    db_session.commit()
    return warehouse, store, vendor, variant


def _create_accepted_po(client, db_session):
    warehouse, store, vendor, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-ap@test.com")
    store_token = login(client, "store", "store-ap@test.com")
    vendor_token = login(client, "vendor", "vendor-ap@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 30, "expected_date": "2026-09-15"},
    )
    pr_ref = pr_resp.json()["data"]["id"]
    rfq_resp = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor.id)]},
    )
    rfq_id = rfq_resp.json()["data"]["id"]
    quote_resp = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={"unit_price": 200, "tax_percent": 10, "discount_percent": 5, "delivery_days": 7, "validity_days": 30, "freight_payer": "vendor"},
    )
    quote_id = quote_resp.json()["data"]["id"]
    select_resp = client.post(f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token), json={"quotation_id": quote_id})
    po_id = select_resp.json()["data"]["po_id"]
    client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_token))
    return warehouse, store, vendor, variant, po_id, wh_token, vendor_token, rfq_resp.json()["data"]["ref_code"]


def test_purchase_order_detail_has_every_field_the_raise_po_screen_reads(client, db_session):
    warehouse, store, vendor, variant, po_id, wh_token, vendor_token, rfq_ref = _create_accepted_po(client, db_session)

    po_resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}", headers=auth_headers(wh_token))
    assert po_resp.status_code == 200
    po = po_resp.json()["data"]
    assert po["qty"] == 30
    assert po["vendor_name"] == vendor.name
    assert po["warehouse"] == warehouse.name
    assert po["tax_percent"] == 10.0
    assert po["discount_percent"] == 5.0
    assert po["rfq_ref"] == rfq_ref
    # delivery_address was a permanently-null column with no writer at all — now defaults to
    # the destination warehouse's own address.
    assert warehouse.address in po["delivery_address"]


def test_vendor_can_create_an_asn_and_it_shows_as_awaiting_inspection(client, db_session):
    warehouse, store, vendor, variant, po_id, wh_token, vendor_token, rfq_ref = _create_accepted_po(client, db_session)

    create_resp = client.post(
        f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_token),
        json={"shipped_qty": 30, "expected_delivery_date": "2026-09-10"},
    )
    assert create_resp.status_code == 201, create_resp.text
    asn_id = create_resp.json()["data"]["id"]
    client.put(f"/api/v1/vendor/asn/{asn_id}/submit", headers=auth_headers(vendor_token))

    # This is exactly the lookup WhPrForwarded.jsx does to decide whether to open the Inspect
    # dialog instead of showing "already fully received" — it must actually find the row.
    list_resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}/asns", headers=auth_headers(wh_token))
    pending = next((a for a in list_resp.json()["data"] if a["status"] == "awaiting_inspection"), None)
    assert pending is not None
    assert pending["id"] == asn_id

    inspect_resp = client.post(
        f"/api/v1/warehouse/purchase-orders/{po_id}/asns/{asn_id}/inspect", headers=auth_headers(wh_token),
        json={"accepted_qty": 30, "rejected_qty": 0, "rejection_reason": None},
    )
    assert inspect_resp.status_code == 200, inspect_resp.text
    assert inspect_resp.json()["data"]["inspection_status"] == "accepted"
    assert inspect_resp.json()["data"]["po_status"] == "Delivered"
    assert inspect_resp.json()["data"]["transfer_order_ref"]  # PO fully received -> auto-dispatched

    after_resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}/asns", headers=auth_headers(wh_token))
    after = next(a for a in after_resp.json()["data"] if a["id"] == asn_id)
    assert after["status"] == "accepted"


def test_vendor_cannot_create_a_second_asn_for_the_same_po(client, db_session):
    # One ASN per PO, once submitted it's locked — a vendor can't file an unrelated second ASN
    # even though the PO status stays "Ready to Ship" (still one of the ASN-eligible statuses).
    warehouse, store, vendor, variant, po_id, wh_token, vendor_token, rfq_ref = _create_accepted_po(client, db_session)

    first = client.post(
        f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_token),
        json={"shipped_qty": 30, "expected_delivery_date": "2026-09-10"},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_token),
        json={"shipped_qty": 30, "expected_delivery_date": "2026-09-20"},
    )
    assert second.status_code == 409, second.text


def test_partial_rejection_unlocks_the_asn_for_vendor_correction_and_resubmission(client, db_session):
    # A partial rejection must not lock the vendor out -- they correct and resubmit the SAME
    # ASN (not a brand new one) for the still-outstanding quantity, and the warehouse can then
    # inspect it again.
    warehouse, store, vendor, variant, po_id, wh_token, vendor_token, rfq_ref = _create_accepted_po(client, db_session)

    create_resp = client.post(
        f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_token),
        json={"shipped_qty": 30, "expected_delivery_date": "2026-09-10"},
    )
    asn_id = create_resp.json()["data"]["id"]
    client.put(f"/api/v1/vendor/asn/{asn_id}/submit", headers=auth_headers(vendor_token))

    inspect_resp = client.post(
        f"/api/v1/warehouse/purchase-orders/{po_id}/asns/{asn_id}/inspect", headers=auth_headers(wh_token),
        json={"accepted_qty": 20, "rejected_qty": 10, "rejection_reason": "Damaged in transit"},
    )
    assert inspect_resp.status_code == 200, inspect_resp.text
    assert inspect_resp.json()["data"]["inspection_status"] == "partial"
    assert inspect_resp.json()["data"]["po_status"] != "Delivered"

    po_resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}", headers=auth_headers(wh_token))
    assert po_resp.json()["data"]["status"] in ("Ready to Ship", "ready_to_ship", "READY_TO_SHIP")

    # Filing a brand new ASN is still refused -- the vendor must correct the existing one.
    blocked = client.post(
        f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_token),
        json={"shipped_qty": 10, "expected_delivery_date": "2026-09-20"},
    )
    assert blocked.status_code == 409, blocked.text

    resubmit_resp = client.put(
        f"/api/v1/vendor/asn/{asn_id}/resubmit", headers=auth_headers(vendor_token),
        json={"shipped_qty": 10, "expected_delivery_date": "2026-09-20"},
    )
    assert resubmit_resp.status_code == 200, resubmit_resp.text
    assert resubmit_resp.json()["data"]["shipped_qty"] == 10

    list_resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_id}/asns", headers=auth_headers(wh_token))
    revised = next(a for a in list_resp.json()["data"] if a["id"] == asn_id)
    assert revised["status"] == "awaiting_inspection"

    second_inspect = client.post(
        f"/api/v1/warehouse/purchase-orders/{po_id}/asns/{asn_id}/inspect", headers=auth_headers(wh_token),
        json={"accepted_qty": 10, "rejected_qty": 0, "rejection_reason": None},
    )
    assert second_inspect.status_code == 200, second_inspect.text
    assert second_inspect.json()["data"]["po_status"] == "Delivered"
