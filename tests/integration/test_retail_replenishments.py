"""Replenishment.jsx has always called GET /replenishments (and /{ref}, /{ref}/tracking) but no
retail router ever exposed that path — every request 404'd and the "Replenishment & Write-off"
screen looked permanently broken, even though the underlying StoreReturnService/repository logic
already existed and was already wired into dependency injection, just never given a router.
"""
from app.services.retail.store_return_service import StoreReturnService
from tests.integration.helpers import (
    auth_headers,
    create_sku_variant,
    create_store,
    create_user,
    create_warehouse,
    link_warehouse_store,
    login,
)


def _setup(db_session):
    warehouse = create_warehouse(db_session, code="WH-RPL-01")
    store = create_store(db_session, code="STR-RPL-01")
    link_warehouse_store(db_session, warehouse, store)
    sku, variant = create_sku_variant(db_session, "SKU-RPL-01", "SKU-RPL-01-BLK-M")
    create_user(db_session, "store", store.id, "store-rpl@test.com", "store-admin")
    db_session.commit()
    return warehouse, store, variant


def test_replenishment_list_get_and_tracking_are_reachable(client, db_session):
    warehouse, store, variant = _setup(db_session)
    store_token = login(client, "store", "store-rpl@test.com")

    sr = StoreReturnService(db_session).create_store_return(
        store.id, warehouse.id, None, variant.id, 5, "Damaged in transit", "replenish"
    )

    list_resp = client.get("/api/v1/retail/replenishments", headers=auth_headers(store_token))
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["data"]
    row = next(i for i in items if i["id"] == sr.ref_code)
    assert row["status"] == "Requested"
    assert row["warehouse"] == warehouse.name
    assert row["qty"] == 5

    detail_resp = client.get(f"/api/v1/retail/replenishments/{sr.ref_code}", headers=auth_headers(store_token))
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["data"]["sku"] == variant.variant_code

    tracking_resp = client.get(f"/api/v1/retail/replenishments/{sr.ref_code}/tracking", headers=auth_headers(store_token))
    assert tracking_resp.status_code == 200, tracking_resp.text
    steps = tracking_resp.json()["data"]["steps"]
    assert steps[0]["label"] == "Requested" and steps[0]["done"] is True and steps[0]["current"] is True


def test_writeoff_replenishment_status(client, db_session):
    warehouse, store, variant = _setup(db_session)
    store_token = login(client, "store", "store-rpl@test.com")

    sr = StoreReturnService(db_session).create_store_return(
        store.id, warehouse.id, None, variant.id, 2, "Defective stock", "writeoff"
    )
    sr.status = "writtenoff"
    db_session.commit()

    detail_resp = client.get(f"/api/v1/retail/replenishments/{sr.ref_code}", headers=auth_headers(store_token))
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["data"]["status"] == "Written Off"
