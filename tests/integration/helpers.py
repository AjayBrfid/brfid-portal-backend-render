"""Shared test data builders — used across integration test modules to stand up a warehouse,
store, or vendor (with its admin login) in a couple of lines rather than repeating the full
registration payload in every test.
"""
import uuid

from app.models.catalog import Sku, SkuStatus, SkuSupplyingVendor, SkuVariant
from app.models.fulfillment import Inventory
from app.models.retail import Store, StoreStatus, StoreType
from app.models.user import User
from app.models.vendor import Vendor, VendorStatus
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseStoreLink, WarehouseStoreLinkStatus, WarehouseVendorLink, WarehouseVendorLinkStatus
from app.core.security import hash_password


def create_warehouse(db, code="WH-TEST-01", **overrides):
    defaults = dict(
        code=code, name="Test Warehouse", state="Maharashtra", city="Mumbai", address="Test Address",
        contact_phone="9000000000", contact_email=f"{code.lower()}@test.com", status=WarehouseStatus.ACTIVE,
        low_stock_warning_units=20, critical_stock_warning_units=5,
    )
    defaults.update(overrides)
    warehouse = Warehouse(**defaults)
    db.add(warehouse)
    db.flush()
    return warehouse


def create_store(db, code="STR-TEST-01", **overrides):
    defaults = dict(
        code=code, name="Test Store", store_type=StoreType.STANDARD, city="Mumbai", state="Maharashtra",
        address="Test Address", contact_phone="9000000001", low_stock_threshold=20, status=StoreStatus.ACTIVE,
    )
    defaults.update(overrides)
    store = Store(**defaults)
    db.add(store)
    db.flush()
    return store


def create_vendor(db, code="VEN-TEST-01", **overrides):
    defaults = dict(
        code=code, name="Test Vendor", contact_person="Vendor Contact", contact_email=f"{code.lower()}@test.com",
        contact_phone="9000000002", state="Gujarat", city="Surat", address="Test Address",
        gst=f"24{uuid.uuid4().hex[:11].upper()}", pan=uuid.uuid4().hex[:10].upper(), status=VendorStatus.ACTIVE,
    )
    defaults.update(overrides)
    vendor = Vendor(**defaults)
    db.add(vendor)
    db.flush()
    return vendor


def create_user(db, portal_type, entity_id, email, role, code=None):
    user = User(
        code=code or f"USR-{uuid.uuid4().hex[:8].upper()}", portal_type=portal_type, entity_id=entity_id,
        email=email, password_hash=hash_password("TestPass123!"), name="Test User", role=role, status="active",
    )
    db.add(user)
    db.flush()
    return user


def create_sku_variant(db, style_code="900", variant_code="SKU-900-BLK-M"):
    sku = Sku(style_code=style_code, name="Test Product", category="Apparel", status=SkuStatus.ACTIVE)
    db.add(sku)
    db.flush()
    variant = SkuVariant(sku_id=sku.id, variant_code=variant_code, colour="Black", size="M")
    db.add(variant)
    db.flush()
    return sku, variant


def link_warehouse_store(db, warehouse, store):
    db.add(WarehouseStoreLink(warehouse_id=warehouse.id, store_id=store.id, status=WarehouseStoreLinkStatus.ACTIVE))
    db.flush()


def link_warehouse_vendor(db, warehouse, vendor):
    db.add(WarehouseVendorLink(warehouse_id=warehouse.id, vendor_id=vendor.id, status=WarehouseVendorLinkStatus.ACTIVE))
    db.flush()


def link_sku_supplying_vendor(db, variant, vendor):
    db.add(SkuSupplyingVendor(sku_variant_id=variant.id, vendor_id=vendor.id))
    db.flush()


def seed_inventory(db, warehouse, variant, on_hand=100, available=100):
    inv = Inventory(warehouse_id=warehouse.id, sku_variant_id=variant.id, on_hand=on_hand, available=available, returns_qty=0)
    db.add(inv)
    db.flush()
    return inv


def login(client, portal_type, email, password="TestPass123!"):
    resp = client.post("/api/v1/auth/login", json={"portal_type": portal_type, "email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
