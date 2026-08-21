"""Aggregates vms-sa-react's old (pre-unification) Super Admin API contract, mounted flat at
`/api/v1/...` (NOT `/api/v1/super-admin/...`) alongside the real unified API — see
vms-sa-react/BACKEND_API_SPEC.md for the authoritative contract this reproduces. `/auth/login`,
`/auth/logout`, and `/auth/me` are already handled directly in app/api/v1/auth/router.py; only
`/auth/password` is added here.
"""
from fastapi import APIRouter

from app.compat.super_admin.activities_router import router as activities_router
from app.compat.super_admin.auth_router import router as auth_router
from app.compat.super_admin.dashboard_router import router as dashboard_router
from app.compat.super_admin.notifications_router import router as notifications_router
from app.compat.super_admin.products_router import router as products_router
from app.compat.super_admin.purchase_orders_router import router as purchase_orders_router
from app.compat.super_admin.quotations_router import router as quotations_router
from app.compat.super_admin.rfqs_router import router as rfqs_router
from app.compat.super_admin.shipments_router import router as shipments_router
from app.compat.super_admin.stock_requests_router import router as stock_requests_router
from app.compat.super_admin.store_inventory_router import router as store_inventory_router
from app.compat.super_admin.stores_router import router as stores_router
from app.compat.super_admin.vendor_catalog_router import router as vendor_catalog_router
from app.compat.super_admin.vendor_stock_router import router as vendor_stock_router
from app.compat.super_admin.vendors_router import router as vendors_router
from app.compat.super_admin.warehouses_router import router as warehouses_router
from app.compat.super_admin.warehouses_router import zone_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(activities_router)
router.include_router(vendors_router)
router.include_router(vendor_stock_router)
router.include_router(vendor_catalog_router)
router.include_router(warehouses_router)
router.include_router(zone_router)
router.include_router(stores_router)
router.include_router(store_inventory_router)
router.include_router(shipments_router)
router.include_router(quotations_router)
router.include_router(stock_requests_router)
router.include_router(products_router)
router.include_router(rfqs_router)
router.include_router(purchase_orders_router)
router.include_router(notifications_router)
