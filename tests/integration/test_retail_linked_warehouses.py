"""GET /retail/warehouses backs the "Choose Warehouse" dropdown in the retail Create Purchase
Request dialog — it must list only warehouses actually linked to the caller's store."""
from tests.integration.helpers import auth_headers, create_store, create_user, create_warehouse, link_warehouse_store, login


def test_list_linked_warehouses_returns_only_linked_ones(client, db_session):
    store = create_store(db_session, code="STR-WH-01")
    linked = create_warehouse(db_session, code="WH-LINK-01", name="Linked Warehouse")
    other = create_warehouse(db_session, code="WH-LINK-02", name="Unlinked Warehouse")
    link_warehouse_store(db_session, linked, store)
    create_user(db_session, "store", store.id, "store-wh@test.com", "store-manager")
    db_session.commit()

    token = login(client, "store", "store-wh@test.com")
    resp = client.get("/api/v1/retail/warehouses", headers=auth_headers(token))
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()["data"]]
    assert names == ["Linked Warehouse"]
    assert other.name not in names


def test_list_linked_warehouses_empty_when_none_linked(client, db_session):
    store = create_store(db_session, code="STR-WH-02")
    create_warehouse(db_session, code="WH-LINK-03")
    create_user(db_session, "store", store.id, "store-wh2@test.com", "store-manager")
    db_session.commit()

    token = login(client, "store", "store-wh2@test.com")
    resp = client.get("/api/v1/retail/warehouses", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["data"] == []
