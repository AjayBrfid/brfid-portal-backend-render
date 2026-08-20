"""Retail's admin-edit-requires-approval workflow: a store-admin's settings change is queued
and only takes effect once approved; a store-manager's own change applies immediately."""
from tests.integration.helpers import auth_headers, create_store, create_user, login


def test_store_admin_change_requires_approval(client, db_session):
    store = create_store(db_session, code="STR-SET-01", name="Original Name")
    create_user(db_session, "store", store.id, "store-admin-set@test.com", "store-admin")
    db_session.commit()
    token = login(client, "store", "store-admin-set@test.com")

    update_resp = client.put(
        "/api/v1/retail/store/organization", headers=auth_headers(token),
        json={"name": "New Name", "gstin": "27NEWGST0001Z5", "address": "New Address"},
    )
    assert update_resp.status_code == 200
    approval_id = update_resp.json()["data"]["approval_id"]
    assert update_resp.json()["data"]["status"] == "waiting_approval"

    # Not applied yet.
    store_resp = client.get("/api/v1/retail/store", headers=auth_headers(token))
    assert store_resp.json()["data"]["name"] == "Original Name"

    approve_resp = client.post(f"/api/v1/retail/store/approvals/{approval_id}/approve", headers=auth_headers(token))
    assert approve_resp.status_code == 204

    store_resp_after = client.get("/api/v1/retail/store", headers=auth_headers(token))
    assert store_resp_after.json()["data"]["name"] == "New Name"


def test_store_manager_change_applies_immediately(client, db_session):
    store = create_store(db_session, code="STR-SET-02", name="Original Name")
    create_user(db_session, "store", store.id, "store-mgr-set@test.com", "store-manager")
    db_session.commit()
    token = login(client, "store", "store-mgr-set@test.com")

    update_resp = client.put(
        "/api/v1/retail/store/organization", headers=auth_headers(token),
        json={"name": "Manager Renamed", "gstin": "27MGRGST0001Z5", "address": "Manager Address"},
    )
    assert update_resp.status_code == 204

    store_resp = client.get("/api/v1/retail/store", headers=auth_headers(token))
    assert store_resp.json()["data"]["name"] == "Manager Renamed"
