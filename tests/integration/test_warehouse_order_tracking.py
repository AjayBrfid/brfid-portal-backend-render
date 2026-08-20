"""GET /warehouse/order-tracking — a genuine aggregation over PurchaseRequest -> RFQ/
TransferOrder state (no endpoint existed for this screen before; WhOrderTracking.jsx was
calling a 404)."""
from app.models.fulfillment import PurchaseRequest
from tests.integration.helpers import (
    auth_headers,
    create_sku_variant,
    create_store,
    create_user,
    create_warehouse,
    link_warehouse_store,
    login,
    seed_inventory,
)


def _setup(db_session, code_suffix):
    warehouse = create_warehouse(db_session, code=f"WH-OT-{code_suffix}")
    store = create_store(db_session, code=f"STR-OT-{code_suffix}")
    link_warehouse_store(db_session, warehouse, store)
    sku, variant = create_sku_variant(db_session, f"SKU-OT-{code_suffix}", f"SKU-OT-{code_suffix}-BLK-M")
    seed_inventory(db_session, warehouse, variant, on_hand=100, available=100)
    create_user(db_session, "warehouse", warehouse.id, f"wh-ot-{code_suffix}@test.com", "wh-admin")
    create_user(db_session, "store", store.id, f"store-ot-{code_suffix}@test.com", "store-admin")
    db_session.commit()
    return warehouse, store, variant


def test_order_tracking_reflects_pr_lifecycle(client, db_session):
    warehouse, store, variant = _setup(db_session, "01")
    wh_token = login(client, "warehouse", "wh-ot-01@test.com")
    store_token = login(client, "store", "store-ot-01@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 10, "expected_date": "2026-09-01"},
    )
    pr_ref = pr_resp.json()["data"]["id"]

    tracking = client.get("/api/v1/warehouse/order-tracking", headers=auth_headers(wh_token))
    assert tracking.status_code == 200
    row = next(r for r in tracking.json()["data"] if r["pr_ref"] == pr_ref)
    assert row["status"] == "Pending Stock Check"
    assert row["store"] == store.name
    assert row["sku"] == variant.variant_code

    fulfil_resp = client.post(f"/api/v1/warehouse/purchase-requests/{pr_ref}/fulfil-from-stock", headers=auth_headers(wh_token))
    to_id = fulfil_resp.json()["data"]["id"]

    tracking2 = client.get("/api/v1/warehouse/order-tracking", headers=auth_headers(wh_token))
    row2 = next(r for r in tracking2.json()["data"] if r["pr_ref"] == pr_ref)
    assert row2["status"] == "In Transit to Retail"

    client.post(
        f"/api/v1/warehouse/transfer-orders/{to_id}/dispatch", headers=auth_headers(wh_token),
        json={"transporter": "BlueDart", "vehicle_number": "MH01AB1234", "packages": 1},
    )
    tracking3 = client.get("/api/v1/warehouse/order-tracking", headers=auth_headers(wh_token))
    row3 = next(r for r in tracking3.json()["data"] if r["pr_ref"] == pr_ref)
    assert row3["status"] == "In Transit to Retail"  # still in transit — dispatched but not yet received

    receiving_resp = client.get("/api/v1/retail/receiving", headers=auth_headers(store_token))
    item_id = receiving_resp.json()["data"][0]["id"]
    client.put(f"/api/v1/retail/receiving/{item_id}", headers=auth_headers(store_token), json={"received": 10, "condition": "Good"})

    tracking4 = client.get("/api/v1/warehouse/order-tracking", headers=auth_headers(wh_token))
    row4 = next(r for r in tracking4.json()["data"] if r["pr_ref"] == pr_ref)
    assert row4["status"] == "Delivered to Retail"

    filtered = client.get("/api/v1/warehouse/order-tracking?status=Delivered to Retail", headers=auth_headers(wh_token))
    assert all(r["status"] == "Delivered to Retail" for r in filtered.json()["data"])


def test_order_tracking_shows_declined_pr(client, db_session):
    warehouse, store, variant = _setup(db_session, "02")
    wh_token = login(client, "warehouse", "wh-ot-02@test.com")
    store_token = login(client, "store", "store-ot-02@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 10, "expected_date": "2026-09-01"},
    )
    pr_ref = pr_resp.json()["data"]["id"]

    from sqlalchemy import select

    pr = db_session.execute(select(PurchaseRequest).where(PurchaseRequest.ref_code == pr_ref)).scalar_one()
    pr.approval_status = "declined"
    db_session.commit()

    tracking = client.get("/api/v1/warehouse/order-tracking", headers=auth_headers(wh_token))
    row = next(r for r in tracking.json()["data"] if r["pr_ref"] == pr_ref)
    assert row["status"] == "Vendor Declined"
