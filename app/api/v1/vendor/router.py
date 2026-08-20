"""Vendor portal router."""
from fastapi import APIRouter

from app.api.v1.auth.notifications_router import build_notifications_router
from app.api.v1.auth.users_router import build_users_router
from app.api.v1.vendor.asn_router import router as asn_router
from app.api.v1.vendor.catalog_router import router as catalog_router
from app.api.v1.vendor.dashboard_router import router as dashboard_router
from app.api.v1.vendor.freight_payment_router import router as freight_payment_router
from app.api.v1.vendor.goods_router import router as goods_router
from app.api.v1.vendor.invoice_router import router as invoice_router
from app.api.v1.vendor.payment_router import router as payment_router
from app.api.v1.vendor.purchase_order_router import router as purchase_order_router
from app.api.v1.vendor.quotation_router import router as quotation_router
from app.api.v1.vendor.registration_router import router as registration_router
from app.api.v1.vendor.rfq_router import router as rfq_router
from app.api.v1.vendor.shipment_router import router as shipment_router
from app.api.v1.vendor.vendor_return_router import router as vendor_return_router

router = APIRouter(prefix="/vendor", tags=["vendor"])
router.include_router(build_users_router("vendor"))
router.include_router(build_notifications_router("vendor"))
router.include_router(registration_router)
router.include_router(rfq_router)
router.include_router(quotation_router)
router.include_router(purchase_order_router)
router.include_router(asn_router)
router.include_router(shipment_router)
router.include_router(vendor_return_router)
router.include_router(invoice_router)
router.include_router(payment_router)
router.include_router(freight_payment_router)
router.include_router(goods_router)
router.include_router(catalog_router)
router.include_router(dashboard_router)
