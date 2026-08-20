"""Super Admin's approve/reject/block/unblock workflows for warehouses, stores, and vendors —
each with server-enforced state-transition guards."""
from tests.integration.helpers import auth_headers, create_user, create_vendor, create_warehouse, login
from app.models.warehouse import WarehouseStatus


def _super_admin_token(client, db_session):
    create_user(db_session, "super_admin", None, "sa@test.com", "super-admin")
    db_session.commit()
    return login(client, "super_admin", "sa@test.com")


def test_approve_pending_warehouse(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-SA-01", status=WarehouseStatus.PENDING_APPROVAL)
    db_session.commit()
    token = _super_admin_token(client, db_session)

    resp = client.post(f"/api/v1/super-admin/warehouses/{warehouse.code}/approve", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "Active"


def test_cannot_approve_already_active_warehouse(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-SA-02", status=WarehouseStatus.ACTIVE)
    db_session.commit()
    token = _super_admin_token(client, db_session)

    resp = client.post(f"/api/v1/super-admin/warehouses/{warehouse.code}/approve", headers=auth_headers(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_block_and_unblock_vendor(client, db_session):
    vendor = create_vendor(db_session, code="VEN-SA-01")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    block_resp = client.post(f"/api/v1/super-admin/vendors/{vendor.code}/block", headers=auth_headers(token))
    assert block_resp.json()["data"]["status"] == "Blocked"

    cannot_reblock = client.post(f"/api/v1/super-admin/vendors/{vendor.code}/block", headers=auth_headers(token))
    assert cannot_reblock.status_code == 409

    unblock_resp = client.post(f"/api/v1/super-admin/vendors/{vendor.code}/unblock", headers=auth_headers(token))
    assert unblock_resp.json()["data"]["status"] == "Active"


def test_blocked_vendor_cannot_log_in(client, db_session):
    vendor = create_vendor(db_session, code="VEN-SA-02")
    create_user(db_session, "vendor", vendor.id, "blocked-vendor@test.com", "vendor-admin")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    client.post(f"/api/v1/super-admin/vendors/{vendor.code}/block", headers=auth_headers(token))

    # The user row itself is still "active" — it's the Vendor entity's status that must be
    # re-checked on every request, not just at login (see get_current_vendor).
    vendor_login = login(client, "vendor", "blocked-vendor@test.com")
    resp = client.get("/api/v1/vendor/goods", headers=auth_headers(vendor_login))
    assert resp.status_code == 403


def test_vendor_list_sort_by_name(client, db_session):
    create_vendor(db_session, code="VEN-SORT-01", name="Zebra Textiles")
    create_vendor(db_session, code="VEN-SORT-02", name="Acme Fabrics")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    asc = client.get("/api/v1/super-admin/vendors?sort=name&order=asc", headers=auth_headers(token)).json()["data"]
    names_asc = [v["name"] for v in asc if v["id"] in ("VEN-SORT-01", "VEN-SORT-02")]
    assert names_asc == ["Acme Fabrics", "Zebra Textiles"]

    desc = client.get("/api/v1/super-admin/vendors?sort=name&order=desc", headers=auth_headers(token)).json()["data"]
    names_desc = [v["name"] for v in desc if v["id"] in ("VEN-SORT-01", "VEN-SORT-02")]
    assert names_desc == ["Zebra Textiles", "Acme Fabrics"]


def test_vendor_list_sort_compat_endpoint(client, db_session):
    create_vendor(db_session, code="VEN-SORT-03", name="Zebra Textiles")
    create_vendor(db_session, code="VEN-SORT-04", name="Acme Fabrics")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    resp = client.get("/api/v1/vendors?sort=name&order=asc", headers=auth_headers(token)).json()["data"]
    names = [v["name"] for v in resp if v["id"] in ("VEN-SORT-03", "VEN-SORT-04")]
    assert names == ["Acme Fabrics", "Zebra Textiles"]


def test_vendor_list_invalid_sort_field_falls_back_to_default(client, db_session):
    create_vendor(db_session, code="VEN-SORT-05")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    resp = client.get("/api/v1/super-admin/vendors?sort=not_a_real_column&order=asc", headers=auth_headers(token))
    assert resp.status_code == 200


def test_vendor_list_default_sort_unchanged_with_no_params(client, db_session):
    create_vendor(db_session, code="VEN-SORT-06")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    resp = client.get("/api/v1/super-admin/vendors", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["meta"]["totalItems"] >= 1


def test_vendor_list_sort_with_pagination(client, db_session):
    for i in range(3):
        create_vendor(db_session, code=f"VEN-SORT-PAGE-0{i}", name=f"PageSort Vendor {i}")
    db_session.commit()
    token = _super_admin_token(client, db_session)

    resp = client.get("/api/v1/super-admin/vendors?sort=name&order=asc&limit=2&page=1", headers=auth_headers(token))
    body = resp.json()
    assert resp.status_code == 200
    assert len(body["data"]) == 2
    assert body["meta"]["limit"] == 2
