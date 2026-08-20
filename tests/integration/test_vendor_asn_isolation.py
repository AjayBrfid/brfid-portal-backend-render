"""Regression test for a cross-vendor data leak found while auditing the v1 vendor ASN
router: GET /api/v1/vendor/asn/{asn_id} had no ownership check at all (AsnService.get_detail
took no vendor_id), so any authenticated vendor could fetch any other vendor's ASN -- including
its nested PO/shipment/invoice data -- by guessing/enumerating a UUID. Same gap existed on the
attachment-upload endpoint. Fixed via AsnService.get_detail_for_vendor / an explicit ownership
check in upload_asn_attachment.
"""
import io

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


def _create_asn_for_vendor_a(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-ISO-01")
    store = create_store(db_session, code="STR-ISO-01")
    vendor_a = create_vendor(db_session, code="VEN-ISO-A")
    link_warehouse_store(db_session, warehouse, store)
    link_warehouse_vendor(db_session, warehouse, vendor_a)
    _, variant = create_sku_variant(db_session, "SKU-ISO-01", "SKU-ISO-01-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor_a)
    create_user(db_session, "warehouse", warehouse.id, "wh-iso@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-iso@test.com", "store-admin")
    create_user(db_session, "vendor", vendor_a.id, "vendor-iso-a@test.com", "vendor-admin")
    db_session.commit()

    wh_token = login(client, "warehouse", "wh-iso@test.com")
    store_token = login(client, "store", "store-iso@test.com")
    vendor_a_token = login(client, "vendor", "vendor-iso-a@test.com")

    pr_ref = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 10, "expected_date": "2026-09-15"},
    ).json()["data"]["id"]
    rfq_id = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor_a.id)]},
    ).json()["data"]["id"]
    quote_id = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_a_token),
        json={"unit_price": 100, "tax_percent": 0, "discount_percent": 0, "delivery_days": 7, "validity_days": 30, "freight_payer": "vendor"},
    ).json()["data"]["id"]
    po_id = client.post(
        f"/api/v1/warehouse/rfqs/{rfq_id}/select-vendor", headers=auth_headers(wh_token), json={"quotation_id": quote_id},
    ).json()["data"]["po_id"]
    client.patch(f"/api/v1/vendor/purchase-orders/{po_id}/accept", headers=auth_headers(vendor_a_token))
    asn_id = client.post(
        f"/api/v1/vendor/asn/purchase-orders/{po_id}", headers=auth_headers(vendor_a_token), json={"shipped_qty": 10},
    ).json()["data"]["id"]
    return asn_id, vendor_a_token


def _vendor_b_token(client, db_session):
    vendor_b = create_vendor(db_session, code="VEN-ISO-B")
    create_user(db_session, "vendor", vendor_b.id, "vendor-iso-b@test.com", "vendor-admin")
    db_session.commit()
    return login(client, "vendor", "vendor-iso-b@test.com")


def test_vendor_cannot_view_another_vendors_asn(client, db_session):
    asn_id, vendor_a_token = _create_asn_for_vendor_a(client, db_session)
    vendor_b_token = _vendor_b_token(client, db_session)

    own = client.get(f"/api/v1/vendor/asn/{asn_id}", headers=auth_headers(vendor_a_token))
    assert own.status_code == 200

    other = client.get(f"/api/v1/vendor/asn/{asn_id}", headers=auth_headers(vendor_b_token))
    assert other.status_code == 404


def test_vendor_cannot_upload_attachment_to_another_vendors_asn(client, db_session):
    asn_id, _ = _create_asn_for_vendor_a(client, db_session)
    vendor_b_token = _vendor_b_token(client, db_session)

    resp = client.post(
        f"/api/v1/vendor/asn/{asn_id}/attachments", headers=auth_headers(vendor_b_token),
        files={"file": ("evidence.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert resp.status_code == 404
