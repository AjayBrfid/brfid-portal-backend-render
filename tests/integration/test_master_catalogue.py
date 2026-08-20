"""Vendor submits a catalog item -> Super Admin approves it (generate_sku) -> it must become
visible in both the warehouse and retail Product Catalogue screens, with no physical stock
required. Covers app/services/catalog_service.py + its two portal routers.
"""
from app.models.vendor import VendorCatalogSubmission
from tests.integration.helpers import auth_headers, create_store, create_user, create_vendor, create_warehouse, login


def _super_admin_token(client, db_session):
    create_user(db_session, "super_admin", None, "sa@test.com", "super-admin")
    db_session.commit()
    return login(client, "super_admin", "sa@test.com")


def _submit_catalog_item(db_session, vendor, **overrides):
    defaults = dict(
        vendor_id=vendor.id, name="Test Kurta", product_type="Ethnic", gender="Women",
        fabric="Cotton", colour="Blue", size="M", gsm=180,
    )
    defaults.update(overrides)
    submission = VendorCatalogSubmission(**defaults)
    db_session.add(submission)
    db_session.flush()
    return submission


def test_approved_catalog_item_visible_in_warehouse_and_retail(client, db_session):
    vendor = create_vendor(db_session, code="VEN-CAT-01")
    warehouse = create_warehouse(db_session, code="WH-CAT-01")
    store = create_store(db_session, code="STR-CAT-01")
    create_user(db_session, "warehouse", warehouse.id, "wh-cat@test.com", "warehouse-manager")
    create_user(db_session, "store", store.id, "store-cat@test.com", "store-manager")
    submission = _submit_catalog_item(db_session, vendor)
    db_session.commit()

    admin_token = _super_admin_token(client, db_session)
    gen_resp = client.post(
        f"/api/v1/super-admin/vendor-catalog/{submission.id}/generate-sku",
        headers=auth_headers(admin_token),
        json={"style_code": "SKU-CAT-01", "hsn": "6104", "gst_rate": 5, "mrp": 999},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    variant_code = gen_resp.json()["data"]["variant_code"]

    wh_token = login(client, "warehouse", "wh-cat@test.com")
    wh_resp = client.get("/api/v1/warehouse/skus/catalogue", headers=auth_headers(wh_token))
    assert wh_resp.status_code == 200
    wh_row = next(r for r in wh_resp.json()["data"] if r["variant_code"] == variant_code)
    # generate_sku must carry the submission's GSM onto the new Sku — it was silently dropped
    # before (Sku.gsm stayed null even though the vendor supplied it at submission time).
    assert wh_row["gsm"] == "180"

    store_token = login(client, "store", "store-cat@test.com")
    retail_resp = client.get("/api/v1/retail/vendor-catalog", headers=auth_headers(store_token))
    assert retail_resp.status_code == 200
    retail_row = next(r for r in retail_resp.json()["data"] if r["variant_code"] == variant_code)
    assert retail_row["supplying_vendor_ids"] == [str(vendor.id)]

    types_resp = client.get("/api/v1/retail/vendor-catalog/types", headers=auth_headers(store_token))
    assert "Ethnic" in types_resp.json()["data"]
    genders_resp = client.get("/api/v1/retail/vendor-catalog/genders", headers=auth_headers(store_token))
    assert "Women" in genders_resp.json()["data"]
    vendors_resp = client.get("/api/v1/retail/vendor-catalog/vendors", headers=auth_headers(store_token))
    assert any(v["id"] == str(vendor.id) for v in vendors_resp.json()["data"])


def test_generate_sku_reuses_existing_sku_for_identical_specification(client, db_session):
    """Two submissions with the same product_type/gender/fabric/gsm/colour/size — even under
    different free-text names — must resolve to one Sku/SkuVariant with two supplying vendors,
    not two duplicate SKUs."""
    vendor = create_vendor(db_session, code="VEN-CAT-03")
    submission_a = _submit_catalog_item(db_session, vendor, name="t-shirt (test 2)", product_type="Men's Wear", fabric="Denim", colour="blue", size="M", gsm=180)
    submission_b = _submit_catalog_item(db_session, vendor, name="t-shirt (Test)", product_type="Men's Wear", fabric="Denim", colour="blue", size="M", gsm=180)
    db_session.commit()

    admin_token = _super_admin_token(client, db_session)
    first = client.post(
        f"/api/v1/super-admin/vendor-catalog/{submission_a.id}/generate-sku",
        headers=auth_headers(admin_token), json={"style_code": "SKU-CAT-03A"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["matched_existing"] is False

    second = client.post(
        f"/api/v1/super-admin/vendor-catalog/{submission_b.id}/generate-sku",
        headers=auth_headers(admin_token), json={"style_code": "SKU-CAT-03B"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["matched_existing"] is True
    assert second.json()["data"]["sku_variant_id"] == first.json()["data"]["sku_variant_id"]
    assert second.json()["data"]["style_code"] == first.json()["data"]["style_code"]

    from app.models.catalog import SkuSupplyingVendor

    links = db_session.query(SkuSupplyingVendor).filter(SkuSupplyingVendor.sku_variant_id == first.json()["data"]["sku_variant_id"]).all()
    assert len(links) == 1  # same vendor supplies both submissions — not duplicated


def test_generate_sku_creates_zero_stock_row_in_every_active_warehouse_and_store(client, db_session):
    """A newly-approved SKU must appear on the warehouse Inventory screen and the retail Stock
    screen as "0 on hand"/"Out" immediately, not stay invisible until that location happens to
    receive a shipment."""
    from app.models.warehouse import WarehouseStatus
    from app.models.retail import StoreStatus

    vendor = create_vendor(db_session, code="VEN-CAT-05")
    wh_never_received = create_warehouse(db_session, code="WH-CAT-06")
    wh_inactive = create_warehouse(db_session, code="WH-CAT-07", status=WarehouseStatus.PENDING_APPROVAL)
    store_never_received = create_store(db_session, code="STR-CAT-06")
    store_inactive = create_store(db_session, code="STR-CAT-07", status=StoreStatus.PENDING_APPROVAL)
    create_user(db_session, "warehouse", wh_never_received.id, "wh-cat3@test.com", "warehouse-manager")
    create_user(db_session, "store", store_never_received.id, "store-cat3@test.com", "store-manager")
    submission = _submit_catalog_item(db_session, vendor, colour="Green")
    db_session.commit()

    admin_token = _super_admin_token(client, db_session)
    gen_resp = client.post(
        f"/api/v1/super-admin/vendor-catalog/{submission.id}/generate-sku",
        headers=auth_headers(admin_token), json={"style_code": "SKU-CAT-05"},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    variant_code = gen_resp.json()["data"]["variant_code"]

    wh_token = login(client, "warehouse", "wh-cat3@test.com")
    inv_resp = client.get("/api/v1/warehouse/inventory", headers=auth_headers(wh_token))
    assert inv_resp.status_code == 200
    row = next(r for r in inv_resp.json()["data"] if r["sku"] == variant_code)
    assert row["on_hand"] == 0
    assert row["available"] == 0
    assert row["status"] == "Out of Stock"

    store_token = login(client, "store", "store-cat3@test.com")
    stock_resp = client.get("/api/v1/retail/products", headers=auth_headers(store_token))
    assert stock_resp.status_code == 200
    store_row = next(r for r in stock_resp.json()["data"] if r["sku"] == variant_code)
    assert store_row["stock"] == 0
    assert store_row["stock_status"] == "Out"

    from app.models.fulfillment import Inventory
    from app.models.retail import StoreInventory

    inactive_wh_row = db_session.get(Inventory, (wh_inactive.id, gen_resp.json()["data"]["sku_variant_id"]))
    assert inactive_wh_row is None  # a not-yet-active warehouse doesn't get a stock row
    inactive_store_row = db_session.get(StoreInventory, (store_inactive.id, gen_resp.json()["data"]["sku_variant_id"]))
    assert inactive_store_row is None  # a not-yet-active store doesn't get a stock row


def test_generate_sku_does_not_merge_different_specifications(client, db_session):
    vendor = create_vendor(db_session, code="VEN-CAT-04")
    submission_a = _submit_catalog_item(db_session, vendor, colour="Blue", gsm=180)
    submission_b = _submit_catalog_item(db_session, vendor, colour="Blue", gsm=123)  # differs only in gsm
    db_session.commit()

    admin_token = _super_admin_token(client, db_session)
    first = client.post(f"/api/v1/super-admin/vendor-catalog/{submission_a.id}/generate-sku", headers=auth_headers(admin_token), json={"style_code": "SKU-CAT-04A"})
    second = client.post(f"/api/v1/super-admin/vendor-catalog/{submission_b.id}/generate-sku", headers=auth_headers(admin_token), json={"style_code": "SKU-CAT-04B"})

    assert second.json()["data"]["matched_existing"] is False
    assert second.json()["data"]["sku_variant_id"] != first.json()["data"]["sku_variant_id"]


def test_unapproved_catalog_submission_not_visible(client, db_session):
    vendor = create_vendor(db_session, code="VEN-CAT-02")
    warehouse = create_warehouse(db_session, code="WH-CAT-02")
    create_user(db_session, "warehouse", warehouse.id, "wh-cat2@test.com", "warehouse-manager")
    _submit_catalog_item(db_session, vendor, name="Not Yet Approved")
    db_session.commit()

    wh_token = login(client, "warehouse", "wh-cat2@test.com")
    resp = client.get("/api/v1/warehouse/skus/catalogue", headers=auth_headers(wh_token))
    assert resp.status_code == 200
    assert all(r["name"] != "Not Yet Approved" for r in resp.json()["data"])
