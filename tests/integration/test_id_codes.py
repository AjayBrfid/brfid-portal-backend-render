"""Every entity's human-readable display code is `{PREFIX}{3-digit number}` via
app/utils/codes.py::next_sequential_code — no dash for most entities (RFQ001, PR001, QT001, ...),
but Vendor/Warehouse/Store codes are dashed (VEN-001, WH-001, STR-001): registration used to
generate both formats depending on the entry point, and the dashed form was the one already
used consistently in seed data and everywhere codes are shown to users, so that's the format
`next_code()` was unified onto. Three entities that never had a working code generator at all
(Quotation, VendorCatalogSubmission, VendorGood) now get one, wired into their create/submit
paths.
"""
import re

from app.models.vendor import VendorCatalogSubmission
from app.repositories.retail_repository import RetailRepository
from app.repositories.vendor_repository import VendorRepository
from app.repositories.warehouse_repository import WarehouseRepository
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


def test_next_code_generators_use_expected_format(db_session):
    assert re.fullmatch(r"WH-\d{3}", WarehouseRepository(db_session).next_code())
    assert re.fullmatch(r"VEN-\d{3}", VendorRepository(db_session).next_code())
    assert re.fullmatch(r"STR-\d{3}", RetailRepository(db_session).next_code())
    assert re.fullmatch(r"GD\d{3}", VendorRepository(db_session).next_good_code())
    assert re.fullmatch(r"CAT\d{3}", VendorRepository(db_session).next_catalog_code())


def test_rfq_and_quotation_ids_and_dates(client, db_session):
    warehouse = create_warehouse(db_session, code="WH-ID-01")
    store = create_store(db_session, code="STR-ID-01")
    vendor = create_vendor(db_session, code="VEN-ID-01")
    link_warehouse_store(db_session, warehouse, store)
    link_warehouse_vendor(db_session, warehouse, vendor)
    sku, variant = create_sku_variant(db_session, "SKU-ID-01", "SKU-ID-01-BLK-M")
    link_sku_supplying_vendor(db_session, variant, vendor)
    create_user(db_session, "warehouse", warehouse.id, "wh-id@test.com", "wh-admin")
    create_user(db_session, "store", store.id, "store-id@test.com", "store-admin")
    create_user(db_session, "vendor", vendor.id, "vendor-id@test.com", "vendor-admin")
    db_session.commit()

    wh_token = login(client, "warehouse", "wh-id@test.com")
    store_token = login(client, "store", "store-id@test.com")
    vendor_token = login(client, "vendor", "vendor-id@test.com")

    pr_resp = client.post(
        "/api/v1/retail/purchase-requests", headers=auth_headers(store_token),
        json={"sku": variant.variant_code, "warehouse": warehouse.name, "qty": 5, "expected_date": "2026-09-20"},
    )
    pr_ref = pr_resp.json()["data"]["id"]
    assert re.fullmatch(r"PR\d{3}", pr_ref)

    rfq_resp = client.post(
        f"/api/v1/warehouse/purchase-requests/{pr_ref}/raise-rfq", headers=auth_headers(wh_token),
        json={"invited_vendor_ids": [str(vendor.id)]},
    )
    rfq = rfq_resp.json()["data"]
    rfq_id = rfq["id"]

    detail_resp = client.get(f"/api/v1/warehouse/rfqs/{rfq_id}", headers=auth_headers(wh_token))
    detail = detail_resp.json()["data"]
    assert re.fullmatch(r"RFQ\d{3}", detail["ref_code"])
    # Issue date = today (when raised); closing date = the PR's own expected/required date —
    # both were previously always null since create_rfq never set them.
    assert detail["issue_date"] is not None
    assert detail["closing_date"] == detail["required_delivery_date"]
    # unit was also always null before — "{quantity} {unit}" rendered as "40 null" in the UI.
    assert detail["unit"] == "Pcs"

    quote_resp = client.post(
        f"/api/v1/vendor/rfqs/{rfq_id}/quotations", headers=auth_headers(vendor_token),
        json={
            "unit_price": 100, "tax_percent": 5, "discount_percent": 0, "delivery_days": 10,
            "validity_days": 30, "freight_payer": "vendor",
        },
    )
    assert quote_resp.status_code in (200, 201), quote_resp.text


def test_vendor_catalog_and_goods_codes_are_generated(db_session):
    vendor = create_vendor(db_session, code="VEN-ID-02")
    db_session.commit()

    from app.services.vendor.catalog_service import CatalogService
    from app.services.vendor.goods_service import GoodsService

    submission = CatalogService(db_session).create(
        vendor.id, None, "Test Product", "Ethnic", "Women", "Cotton", "Blue", "M", 180, None,
    )
    assert re.fullmatch(r"CAT\d{3}", submission.code)

    good = GoodsService(db_session).create(vendor.id, "Test Fabric", "Fabric", "Meters", 100, 50, None)
    assert re.fullmatch(r"GD\d{3}", good["code"])
