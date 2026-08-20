"""Smoke tests for the backward-compatibility layer (app/compat/) that lets vms-react and
vms-sa-react run unmodified against the unified backend — see app/compat/__init__.py's
module docstring. These check contract shape (paths, payload keys, camelCase field names), not
full business-rule coverage (that's already covered by the real /api/v1/vendor|super-admin/...
routes these delegate to).
"""
from tests.integration.helpers import create_user, create_vendor, create_warehouse


def _legacy_login(client, path, payload):
    resp = client.post(path, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_vendor_legacy_login_returns_old_contract_shape(client, db_session):
    vendor = create_vendor(db_session, code="VEN-COMPAT-01")
    create_user(db_session, "vendor", vendor.id, "vendor-compat@test.com", "vendor-admin")
    db_session.commit()

    data = _legacy_login(client, "/auth/login", {"email": "vendor-compat@test.com", "password": "TestPass123!"})

    assert "accessToken" in data and "refreshToken" in data
    assert data["vendor"]["id"] == vendor.code
    assert data["vendor"]["company"]["name"] == vendor.name
    assert data["vendor"]["contact"]["person"] == vendor.contact_person
    assert data["vendor"]["status"] == "Active"
    assert data["vendor"]["approved"] is True


def test_vendor_legacy_dashboard_and_rfqs_are_camel_case(client, db_session):
    vendor = create_vendor(db_session, code="VEN-COMPAT-02")
    create_user(db_session, "vendor", vendor.id, "vendor-compat2@test.com", "vendor-admin")
    db_session.commit()

    data = _legacy_login(client, "/auth/login", {"email": "vendor-compat2@test.com", "password": "TestPass123!"})
    headers = {"Authorization": f"Bearer {data['accessToken']}"}

    kpis = client.get("/dashboard/kpis?period=month", headers=headers)
    assert kpis.status_code == 200
    body = kpis.json()["data"]
    assert set(body.keys()) == {
        "availableRfqs", "submittedQuotes", "acceptedPos", "pendingShipments", "pendingPayments", "invoicesDue",
    }

    rfqs = client.get("/rfqs?limit=20", headers=headers)
    assert rfqs.status_code == 200
    assert rfqs.json()["meta"].keys() >= {"page", "limit", "totalItems", "totalPages"}


def test_super_admin_legacy_login_returns_old_contract_shape(client, db_session):
    user = create_user(db_session, "super_admin", None, "sa-compat@test.com", "super-admin")
    db_session.commit()

    data = _legacy_login(client, "/api/v1/auth/login", {"email": "sa-compat@test.com", "password": "TestPass123!"})

    assert "token" in data
    assert data["user"] == {"name": user.name, "role": user.role}


def test_super_admin_legacy_vendor_approve_reject_block_roundtrip(client, db_session):
    from app.models.vendor import VendorStatus

    sa = create_user(db_session, "super_admin", None, "sa-compat2@test.com", "super-admin")
    vendor = create_vendor(db_session, code="VEN-COMPAT-03", status=VendorStatus.PENDING_APPROVAL)
    db_session.commit()

    data = _legacy_login(client, "/api/v1/auth/login", {"email": "sa-compat2@test.com", "password": "TestPass123!"})
    headers = {"Authorization": f"Bearer {data['token']}"}

    listed = client.get("/api/v1/vendors?limit=1000", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["meta"].keys() >= {"page", "limit", "total", "totalPages"}

    approve = client.post(f"/api/v1/vendors/{vendor.code}/approve", headers=headers)
    assert approve.status_code == 200
    assert approve.json()["data"]["status"] == "Active"

    block = client.post(f"/api/v1/vendors/{vendor.code}/block", headers=headers)
    assert block.status_code == 200
    assert block.json()["data"]["status"] == "Blocked"


def test_vendor_legacy_catalog_create_uses_the_linked_goods_name(client, db_session):
    """CatalogPage.jsx submits from an existing Goods item and never sends its own `name` in
    the payload (its "Product" field is just a disabled display of the good's name) — the
    compat route must use that good's real name rather than synthesizing "{type} - {colour}"."""
    from app.models.vendor import GoodsUnit, GoodsCategory, StockStatus, VendorGood

    vendor = create_vendor(db_session, code="VEN-COMPAT-05")
    create_user(db_session, "vendor", vendor.id, "vendor-compat5@test.com", "vendor-admin")
    good = VendorGood(
        vendor_id=vendor.id, name="Premium Denim Jacket", category=GoodsCategory.FABRIC, unit=GoodsUnit.PCS,
        quantity=100, price=500, stock_status=StockStatus.IN_STOCK,
    )
    db_session.add(good)
    db_session.commit()

    data = _legacy_login(client, "/auth/login", {"email": "vendor-compat5@test.com", "password": "TestPass123!"})
    headers = {"Authorization": f"Bearer {data['accessToken']}"}

    resp = client.post(
        "/catalog",
        headers=headers,
        json={"goodsId": str(good.id), "productType": "Outerwear", "gender": "Men", "fabric": "Denim", "colour": "Indigo", "size": "L", "gsm": 320},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["name"] == "Premium Denim Jacket"


def test_super_admin_legacy_dashboard_summary_counts_real_rows(client, db_session):
    create_user(db_session, "super_admin", None, "sa-compat3@test.com", "super-admin")
    create_vendor(db_session, code="VEN-COMPAT-04")
    create_warehouse(db_session, code="WH-COMPAT-01")
    db_session.commit()

    data = _legacy_login(client, "/api/v1/auth/login", {"email": "sa-compat3@test.com", "password": "TestPass123!"})
    headers = {"Authorization": f"Bearer {data['token']}"}

    summary = client.get("/api/v1/dashboard/summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()["data"]
    assert body["totalVendors"] == 1
    assert body["totalWarehouses"] == 1
