"""Warehouse ASN-list and invoice-list po_id filtering — was applied in Python AFTER pagination
(fetch page N of ALL the warehouse's ASNs/invoices, then filter that page down to the requested
po_id), so a PO's own ASN/invoice could silently vanish from its own detail page if enough OTHER
ASNs/invoices existed elsewhere in the warehouse to push it onto a later page, and the reported
`meta.totalItems` reflected the post-filter subset of that one page rather than the true total.
Fixed by pushing the po_id filter into the repository's SQL WHERE clause, before pagination.
"""
from datetime import date
from decimal import Decimal

from app.models.shipping import Invoice
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


def _accepted_po(client, db_session, suffix):
    warehouse = create_warehouse(db_session, code=f"WH-LP-{suffix}")
    store = create_store(db_session, code=f"STR-LP-{suffix}")
    vendor = create_vendor(db_session, code=f"VEN-LP-{suffix}")
    link_warehouse_store(db_session, warehouse, store)
    link_warehouse_vendor(db_session, warehouse, vendor)
    _, variant = create_sku_variant(db_session, f"SKU-LP-{suffix}", f"SKU-LP-{suffix}-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor)
    create_user(db_session, "warehouse", warehouse.id, f"wh-lp-{suffix}@test.com", "wh-admin")
    create_user(db_session, "store", store.id, f"store-lp-{suffix}@test.com", "store-admin")
    create_user(db_session, "vendor", vendor.id, f"vendor-lp-{suffix}@test.com", "vendor-admin")
    db_session.commit()

    wh_token = login(client, "warehouse", f"wh-lp-{suffix}@test.com")
    store_token = login(client, "store", f"store-lp-{suffix}@test.com")
    vendor_token = login(client, "vendor", f"vendor-lp-{suffix}@test.com")

    pr_ref = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 10, "expected_date": "2026-09-15"},
    ).json()["data"]["id"]
    rfq_id = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor.id)]},
    ).json()["data"]["id"]
    quote_id = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={"unit_price": 100, "tax_percent": 0, "discount_percent": 0, "delivery_days": 7, "validity_days": 30, "freight_payer": "vendor"},
    ).json()["data"]["id"]
    po_id = client.post(
        f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token), json={"quotation_id": quote_id},
    ).json()["data"]["po_id"]
    client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_token))
    return po_id, wh_token, vendor_token, vendor.id


def test_asn_list_for_one_po_ignores_other_pos_and_reports_correct_total(client, db_session):
    po_1, wh_token_1, vendor_token_1, _ = _accepted_po(client, db_session, "01")
    po_2, wh_token_2, vendor_token_2, _ = _accepted_po(client, db_session, "02")

    asn_1 = client.post(f"/api/v1/vendor/asn/purchase-orders/{po_1}", headers=auth_headers(vendor_token_1), json={"shipped_qty": 10}).json()["data"]["id"]
    client.post(f"/api/v1/vendor/asn/purchase-orders/{po_2}", headers=auth_headers(vendor_token_2), json={"shipped_qty": 10})

    # limit=1 forces pagination to matter -- if the po_id filter were still applied client-side
    # after pagination, a small page size combined with another warehouse's ASN sorting ahead of
    # this one could hide it entirely.
    resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_1}/asns?limit=1&page=1", headers=auth_headers(wh_token_1))
    body = resp.json()
    assert resp.status_code == 200
    assert body["meta"]["totalItems"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == asn_1


def test_asn_list_no_filter_pagination_interaction(client, db_session):
    po_1, wh_token_1, vendor_token_1, _ = _accepted_po(client, db_session, "03")
    client.post(f"/api/v1/vendor/asn/purchase-orders/{po_1}", headers=auth_headers(vendor_token_1), json={"shipped_qty": 10})

    resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_1}/asns", headers=auth_headers(wh_token_1))
    body = resp.json()
    assert resp.status_code == 200
    assert body["meta"]["totalItems"] == 1
    assert body["meta"]["limit"] == 20


def test_invoice_list_for_one_po_ignores_other_pos_and_reports_correct_total(client, db_session):
    po_1, wh_token_1, _, vendor_id_1 = _accepted_po(client, db_session, "04")
    po_2, wh_token_2, _, vendor_id_2 = _accepted_po(client, db_session, "05")

    inv_1 = Invoice(
        po_id=po_1, vendor_id=vendor_id_1, invoice_number="INV-LP-04", invoice_date=date(2026, 8, 1),
        base_amount=Decimal("1000"), gst_amount=Decimal("0"), total_amount=Decimal("1000"),
    )
    inv_2 = Invoice(
        po_id=po_2, vendor_id=vendor_id_2, invoice_number="INV-LP-05", invoice_date=date(2026, 8, 1),
        base_amount=Decimal("2000"), gst_amount=Decimal("0"), total_amount=Decimal("2000"),
    )
    db_session.add_all([inv_1, inv_2])
    db_session.commit()

    resp = client.get(f"/api/v1/warehouse/purchase-orders/{po_1}/invoices?limit=1&page=1", headers=auth_headers(wh_token_1))
    body = resp.json()
    assert resp.status_code == 200
    assert body["meta"]["totalItems"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["invoice_number"] == "INV-LP-04"
