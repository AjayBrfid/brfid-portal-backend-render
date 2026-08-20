"""Super Admin portal router. Core-ops approval workflows (warehouse/store, zones, store
inventory) plus vendor management (approve/reject/block/unblock, vendor stock, vendor catalog +
generate_sku)."""
from fastapi import APIRouter

from app.api.v1.auth.notifications_router import build_notifications_router
from app.api.v1.super_admin.store_inventory_router import router as store_inventory_router
from app.api.v1.super_admin.stores_router import router as stores_router
from app.api.v1.super_admin.vendor_catalog_router import vendor_catalog_router, vendor_stock_router
from app.api.v1.super_admin.vendors_router import router as vendors_router
from app.api.v1.super_admin.warehouses_router import router as warehouses_router

router = APIRouter(prefix="/super-admin", tags=["super-admin"])
router.include_router(build_notifications_router("super_admin"))
router.include_router(warehouses_router)
router.include_router(stores_router)
router.include_router(store_inventory_router)
router.include_router(vendors_router)
router.include_router(vendor_stock_router)
router.include_router(vendor_catalog_router)
