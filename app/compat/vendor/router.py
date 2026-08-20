"""Aggregates vms-react's old (pre-unification) Vendor API contract, mounted at ROOT (no
prefix at all) alongside the real unified API under /api/v1/... — see
vms-react/API_SPECIFICATION.md for the contract this reproduces (with corrections for a few
endpoints that vms-react's actual current code already deviates from that doc — see each
router's own docstring)."""
from fastapi import APIRouter

from app.compat.vendor.asn_router import router as asn_router
from app.compat.vendor.auth_router import router as auth_router
from app.compat.vendor.catalog_router import router as catalog_router
from app.compat.vendor.dashboard_router import router as dashboard_router
from app.compat.vendor.freight_payment_router import router as freight_payment_router
from app.compat.vendor.goods_router import router as goods_router
from app.compat.vendor.invoice_router import router as invoice_router
from app.compat.vendor.notification_router import router as notification_router
from app.compat.vendor.payment_router import router as payment_router
from app.compat.vendor.profile_router import router as profile_router
from app.compat.vendor.purchase_order_router import router as purchase_order_router
from app.compat.vendor.quotation_router import router as quotation_router
from app.compat.vendor.return_router import router as return_router
from app.compat.vendor.rfq_router import router as rfq_router
from app.compat.vendor.shipment_router import router as shipment_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(profile_router)
router.include_router(dashboard_router)
router.include_router(rfq_router)
router.include_router(quotation_router)
router.include_router(purchase_order_router)
router.include_router(asn_router)
router.include_router(shipment_router)
router.include_router(return_router)
router.include_router(freight_payment_router)
router.include_router(invoice_router)
router.include_router(payment_router)
router.include_router(goods_router)
router.include_router(catalog_router)
router.include_router(notification_router)
