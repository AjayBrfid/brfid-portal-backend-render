"""The core warehouse<->retail fulfilment chain: a store's purchase request fulfilled from
warehouse stock, dispatched, and received — the same flow verified manually during Phase 3.
"""
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


def _setup(db_session):
    warehouse = create_warehouse(db_session, code="WH-FF-01")
    store = create_store(db_session, code="STR-FF-01")
    link_warehouse_store(db_session, warehouse, store)
    sku, variant = create_sku_variant(db_session, "SKU-FF-01", "SKU-FF-01-BLK-M")
    seed_inventory(db_session, warehouse, variant, on_hand=100, available=100)
    create_user(db_session, "warehouse", warehouse.id, "wh-ff@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-ff@test.com", "store-admin")
    db_session.commit()
    return warehouse, store, variant


def test_purchase_request_fulfil_dispatch_receive(client, db_session):
    warehouse, store, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-ff@test.com")
    store_token = login(client, "store", "store-ff@test.com")

    # Store creates a purchase request against the linked warehouse.
    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 10, "expected_date": "2026-09-01"},
    )
    assert pr_resp.status_code == 201, pr_resp.text
    pr_ref = pr_resp.json()["data"]["id"]

    # Warehouse sees it and fulfils it from stock.
    list_resp = client.get("/api/v1/warehouse/purchase-requests", headers=auth_headers(wh_token))
    assert list_resp.json()["meta"]["totalItems"] == 1

    fulfil_resp = client.post(f"/api/v1/warehouse/purchase-requests/{pr_ref}/fulfil-from-stock", headers=auth_headers(wh_token))
    assert fulfil_resp.status_code == 200, fulfil_resp.text
    transfer_order = fulfil_resp.json()["data"]
    assert transfer_order["qty"] == 10
    assert transfer_order["status"] == "Pending"
    to_id = transfer_order["id"]

    # Inventory dropped by exactly the fulfilled quantity.
    inv_resp = client.get("/api/v1/warehouse/inventory", headers=auth_headers(wh_token))
    row = inv_resp.json()["data"][0]
    assert row["on_hand"] == 90
    assert row["available"] == 90

    # Warehouse dispatches the transfer order.
    dispatch_resp = client.post(
        f"/api/v1/warehouse/transfer-orders/{to_id}/dispatch", headers=auth_headers(wh_token),
        json={"transporter": "BlueDart", "vehicle_number": "MH01AB1234", "packages": 1},
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["data"]["status"] == "Dispatched"

    # Store receives it: recording a "Good" count increases store stock and marks the
    # transfer order Delivered.
    receiving_resp = client.get("/api/v1/retail/receiving", headers=auth_headers(store_token))
    items = receiving_resp.json()["data"]
    assert len(items) == 1
    item_id = items[0]["id"]

    record_resp = client.put(f"/api/v1/retail/receiving/{item_id}", headers=auth_headers(store_token), json={"received": 10, "condition": "Good"})
    assert record_resp.status_code == 200
    assert record_resp.json()["data"]["status"] == "Verified"

    products_resp = client.get("/api/v1/retail/products", headers=auth_headers(store_token))
    product = products_resp.json()["data"][0]
    assert product["stock"] == 10

    to_detail = client.get(f"/api/v1/warehouse/transfer-orders/{to_id}", headers=auth_headers(wh_token))
    assert to_detail.json()["data"]["status"] == "Delivered"


def test_fulfil_from_stock_insufficient_inventory_rejected(client, db_session):
    warehouse, store, variant = _setup(db_session)
    wh_token = login(client, "warehouse", "wh-ff@test.com")
    store_token = login(client, "store", "store-ff@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 500, "expected_date": "2026-09-01"},
    )
    pr_ref = pr_resp.json()["data"]["id"]

    fulfil_resp = client.post(f"/api/v1/warehouse/purchase-requests/{pr_ref}/fulfil-from-stock", headers=auth_headers(wh_token))
    assert fulfil_resp.status_code == 409
    assert fulfil_resp.json()["error"]["code"] == "CONFLICT"
