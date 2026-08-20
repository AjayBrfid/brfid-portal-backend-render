from tests.integration.helpers import auth_headers, create_user, create_warehouse, login


def test_login_success_and_me(client, db_session):
    warehouse = create_warehouse(db_session)
    create_user(db_session, "warehouse", warehouse.id, "wh@test.com", "wh-admin")
    db_session.commit()

    token = login(client, "warehouse", "wh@test.com")
    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["email"] == "wh@test.com"
    assert data["entity_name"] == warehouse.name


def test_login_wrong_password_rejected(client, db_session):
    warehouse = create_warehouse(db_session)
    create_user(db_session, "warehouse", warehouse.id, "wh2@test.com", "wh-admin")
    db_session.commit()

    resp = client.post("/api/v1/auth/login", json={"portal_type": "warehouse", "email": "wh2@test.com", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_refresh_and_logout_revokes_token(client, db_session):
    warehouse = create_warehouse(db_session)
    create_user(db_session, "warehouse", warehouse.id, "wh3@test.com", "wh-admin")
    db_session.commit()

    login_resp = client.post("/api/v1/auth/login", json={"portal_type": "warehouse", "email": "wh3@test.com", "password": "TestPass123!"})
    access = login_resp.json()["data"]["access_token"]
    refresh = login_resp.json()["data"]["refresh_token"]

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert refresh_resp.status_code == 200

    logout_resp = client.post("/api/v1/auth/logout", json={"refresh_token": refresh}, headers=auth_headers(access))
    assert logout_resp.status_code == 200

    revoked_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert revoked_resp.status_code == 401


def test_cross_portal_rbac_rejected(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-RBAC-01")
    create_user(db_session, "warehouse", warehouse.id, "wh-rbac@test.com", "wh-admin")
    db_session.commit()

    token = login(client, "warehouse", "wh-rbac@test.com")
    resp = client.get("/api/v1/vendor/goods", headers=auth_headers(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
