"""Seed representative data for all four portals — run once against a freshly-migrated
database to get a working demo/dev environment out of the box.

Usage:
    python scripts/seed.py

Idempotent: safe to re-run — checks for existing rows by unique code/email before inserting.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.catalog import Sku, SkuStatus, SkuSupplyingVendor, SkuVariant
from app.models.fulfillment import Inventory, PurchaseRequest
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus, Quotation, QuotationStatus, Rfq, RfqInvitedVendor, RfqStatus
from app.models.retail import Store, StoreStatus, StoreType
from app.models.user import User
from app.models.vendor import Vendor, VendorStatus
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseStoreLink, WarehouseStoreLinkStatus, WarehouseVendorLink, WarehouseVendorLinkStatus


def get_or_create_user(db, code, portal_type, entity_id, email, name, role):
    user = db.query(User).filter(User.email == email, User.portal_type == portal_type).first()
    if user:
        return user
    user = User(code=code, portal_type=portal_type, entity_id=entity_id, email=email, password_hash=hash_password("Password123!"), name=name, role=role, status="active")
    db.add(user)
    db.flush()
    return user


def main():
    db = SessionLocal()
    try:
        # --- Super Admin ---
        get_or_create_user(db, "USR-SA-0001", "super_admin", None, "admin@brfid.com", "Platform Admin", "super-admin")

        # --- Warehouse ---
        warehouse = db.query(Warehouse).filter(Warehouse.code == "WH-001").first()
        if not warehouse:
            warehouse = Warehouse(
                code="WH-001", name="Mumbai Central Warehouse", business_type="Private Limited", company_name="Acme Logistics Pvt Ltd",
                pan="ABCDE1234F", gstin="27ABCDE1234F1Z5", state="Maharashtra", city="Mumbai", address="123 Industrial Area, Andheri East",
                pincode="400069", contact_phone="9876543210", contact_email="wh-admin@brfid.com",
                status=WarehouseStatus.ACTIVE, low_stock_warning_units=20, critical_stock_warning_units=5,
            )
            db.add(warehouse)
            db.flush()
        get_or_create_user(db, "USR-WH-0001", "warehouse", warehouse.id, "wh-admin@brfid.com", "Warehouse Admin", "wh-admin")

        # --- Store ---
        store = db.query(Store).filter(Store.code == "STR-0001").first()
        if not store:
            store = Store(
                code="STR-0001", name="Downtown Flagship Store", store_type=StoreType.FLAGSHIP, business_type="Proprietorship",
                pan="XYZAB5678C", region="West", city="Mumbai", state="Maharashtra", address="45 Market Street, Bandra",
                pincode="400050", gstin="27XYZAB5678C1Z5", contact_phone="9123456780", low_stock_threshold=20,
                status=StoreStatus.ACTIVE,
            )
            db.add(store)
            db.flush()
        get_or_create_user(db, "USR-ST-0001", "store", store.id, "store-admin@brfid.com", "Store Admin", "store-admin")

        existing_link = db.query(WarehouseStoreLink).filter(WarehouseStoreLink.warehouse_id == warehouse.id, WarehouseStoreLink.store_id == store.id).first()
        if not existing_link:
            db.add(WarehouseStoreLink(warehouse_id=warehouse.id, store_id=store.id, status=WarehouseStoreLinkStatus.ACTIVE))

        # --- Vendor ---
        vendor = db.query(Vendor).filter(Vendor.code == "VEN-001").first()
        if not vendor:
            vendor = Vendor(
                code="VEN-001", name="Textile Supplies Co", category="Fabric", contact_person="Vendor Admin",
                contact_email="vendor-admin@brfid.com", contact_phone="9988776655", state="Gujarat", city="Surat",
                address="78 Textile Market", gst="24VENDR5678G1Z5", pan="VENDR5678G", status=VendorStatus.ACTIVE,
                rating=4.5, lead_time_days=7,
            )
            db.add(vendor)
            db.flush()
        get_or_create_user(db, "USR-VN-0001", "vendor", vendor.id, "vendor-admin@brfid.com", "Vendor Admin", "vendor-admin")

        existing_vendor_link = db.query(WarehouseVendorLink).filter(WarehouseVendorLink.warehouse_id == warehouse.id, WarehouseVendorLink.vendor_id == vendor.id).first()
        if not existing_vendor_link:
            db.add(WarehouseVendorLink(warehouse_id=warehouse.id, vendor_id=vendor.id, status=WarehouseVendorLinkStatus.ACTIVE))

        # --- Catalog: SKU + variant, linked to vendor as supplier ---
        sku = db.query(Sku).filter(Sku.style_code == "001").first()
        if not sku:
            sku = Sku(style_code="001", name="Cotton Crew-Neck T-Shirt", category="Apparel", gender="Unisex", fabric="100% Cotton", hsn="6109", gst_rate=5, mrp=499, status=SkuStatus.ACTIVE)
            db.add(sku)
            db.flush()
        variant = db.query(SkuVariant).filter(SkuVariant.variant_code == "SKU-001-BLK-M").first()
        if not variant:
            variant = SkuVariant(sku_id=sku.id, variant_code="SKU-001-BLK-M", colour="Black", size="M")
            db.add(variant)
            db.flush()
        existing_supply = db.query(SkuSupplyingVendor).filter(SkuSupplyingVendor.sku_variant_id == variant.id, SkuSupplyingVendor.vendor_id == vendor.id).first()
        if not existing_supply:
            db.add(SkuSupplyingVendor(sku_variant_id=variant.id, vendor_id=vendor.id))

        # --- Warehouse inventory ---
        inv = db.get(Inventory, (warehouse.id, variant.id))
        if not inv:
            db.add(Inventory(warehouse_id=warehouse.id, sku_variant_id=variant.id, on_hand=200, available=200, returns_qty=0))

        # --- A sample purchase request + RFQ + quotation + PO, to show the full chain ---
        pr = db.query(PurchaseRequest).filter(PurchaseRequest.ref_code == "PR-0001").first()
        if not pr:
            pr = PurchaseRequest(
                ref_code="PR-0001", store_id=store.id, warehouse_id=warehouse.id, sku_variant_id=variant.id,
                requested_qty=50, required_by=date.today() + timedelta(days=14), priority="Medium", approval_status="pending",
            )
            db.add(pr)
            db.flush()

        rfq = db.query(Rfq).filter(Rfq.ref_code == "RFQ-0001").first()
        if not rfq:
            rfq = Rfq(
                ref_code="RFQ-0001", pr_id=pr.id, warehouse_id=warehouse.id, sku_variant_id=variant.id, quantity=50,
                required_delivery_date=date.today() + timedelta(days=14), status=RfqStatus.AWAITING_QUOTATIONS,
            )
            db.add(rfq)
            db.flush()
            db.add(RfqInvitedVendor(rfq_id=rfq.id, vendor_id=vendor.id))

        quotation = db.query(Quotation).filter(Quotation.rfq_id == rfq.id, Quotation.vendor_id == vendor.id).first()
        if not quotation:
            quotation = Quotation(
                rfq_id=rfq.id, vendor_id=vendor.id, unit_price=150, tax_percent=5, discount_percent=0,
                total_amount=7875, delivery_days=7, validity_days=30, freight_payer="vendor", status=QuotationStatus.SUBMITTED,
            )
            db.add(quotation)

        db.commit()
        print("Seed complete:")
        print(f"  Super Admin login: admin@brfid.com / Password123!")
        print(f"  Warehouse login:   wh-admin@brfid.com / Password123!  (portal_type=warehouse)")
        print(f"  Store login:       store-admin@brfid.com / Password123!  (portal_type=store)")
        print(f"  Vendor login:      vendor-admin@brfid.com / Password123!  (portal_type=vendor)")
        print("  Sample chain: PR-0001 -> RFQ-0001 -> quotation (awaiting vendor selection)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
