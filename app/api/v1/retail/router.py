"""Retail portal router. Shipments/replenishment/reports/dashboard land in a later pass —
core products/stock/discounts, purchase requests, receiving, and store settings/registration
are wired in now (Phase 3). Note: URL prefix is `/retail` but the stored `users.portal_type`
value is `store` (see app/constants/portals.py) — this mapping must stay consistent everywhere
auth is checked."""
from fastapi import APIRouter

from app.api.v1.auth.notifications_router import build_notifications_router
from app.api.v1.auth.users_router import build_users_router
from app.api.v1.retail.dashboard_router import router as dashboard_router
from app.api.v1.retail.products_router import discounts_router, products_router, stock_router
from app.api.v1.retail.purchase_requests_router import router as purchase_requests_router
from app.api.v1.retail.receiving_router import router as receiving_router
from app.api.v1.retail.replenishment_router import router as replenishment_router
from app.api.v1.retail.reports_router import router as reports_router
from app.api.v1.retail.store_settings_router import router as store_settings_router
from app.api.v1.retail.stores_router import router as stores_router
from app.api.v1.retail.vendor_catalog_router import router as vendor_catalog_router

router = APIRouter(prefix="/retail", tags=["retail"])
router.include_router(build_users_router("store"))
router.include_router(build_notifications_router("store"))
router.include_router(stores_router)
router.include_router(store_settings_router)
router.include_router(products_router)
router.include_router(stock_router)
router.include_router(discounts_router)
router.include_router(vendor_catalog_router)
router.include_router(purchase_requests_router)
router.include_router(receiving_router)
router.include_router(replenishment_router)
router.include_router(dashboard_router)
router.include_router(reports_router)
