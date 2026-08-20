"""Warehouse portal router — core-ops (Phase 3) plus warehouse-facing vendor/procurement
actions: RFQ issue, PO tracking, ASN inspection, vendor returns (Phase 4)."""
from fastapi import APIRouter

from app.api.v1.auth.notifications_router import build_notifications_router
from app.api.v1.auth.users_router import build_users_router
from app.api.v1.warehouse.asn_router import router as asn_router
from app.api.v1.warehouse.audit_log_router import router as audit_log_router
from app.api.v1.warehouse.catalogue_router import router as catalogue_router
from app.api.v1.warehouse.dashboard_router import router as dashboard_router
from app.api.v1.warehouse.inventory_router import router as inventory_router
from app.api.v1.warehouse.invoices_status_router import router as invoices_status_router
from app.api.v1.warehouse.order_tracking_router import router as order_tracking_router
from app.api.v1.warehouse.purchase_orders_router import router as purchase_orders_router
from app.api.v1.warehouse.purchase_requests_router import router as purchase_requests_router
from app.api.v1.warehouse.reports_router import router as reports_router
from app.api.v1.warehouse.rfq_router import router as rfq_router
from app.api.v1.warehouse.store_returns_router import router as store_returns_router
from app.api.v1.warehouse.transfer_orders_router import router as transfer_orders_router
from app.api.v1.warehouse.vendor_returns_router import router as vendor_returns_router
from app.api.v1.warehouse.warehouse_router import router as warehouse_router

router = APIRouter(prefix="/warehouse", tags=["warehouse"])
router.include_router(build_users_router("warehouse"))
router.include_router(build_notifications_router("warehouse"))
router.include_router(warehouse_router)
router.include_router(dashboard_router)
router.include_router(reports_router)
router.include_router(inventory_router)
router.include_router(catalogue_router)
router.include_router(purchase_requests_router)
router.include_router(order_tracking_router)
router.include_router(transfer_orders_router)
router.include_router(store_returns_router)
router.include_router(audit_log_router)
router.include_router(rfq_router)
router.include_router(purchase_orders_router)
router.include_router(asn_router)
router.include_router(vendor_returns_router)
router.include_router(invoices_status_router)
