from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.models.vendor import Vendor, VendorStatus
from app.repositories.vendor_repository import VendorRepository
from app.services.vendor.asn_service import AsnService
from app.services.vendor.catalog_service import CatalogService
from app.services.vendor.goods_service import GoodsService
from app.services.vendor.payment_service import FreightPaymentService, PaymentService
from app.services.vendor.purchase_order_service import PurchaseOrderService
from app.services.vendor.quotation_service import QuotationService
from app.services.vendor.rfq_service import RfqService
from app.services.vendor.shipment_service import ShipmentService
from app.services.vendor.vendor_return_service import VendorReturnService
from app.services.vendor.vendor_service import VendorRegistrationService


def get_current_vendor(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> Vendor:
    if user.portal_type.value != "vendor" or not user.entity_id:
        raise ForbiddenException("This endpoint requires a vendor account")
    vendor = VendorRepository(session).get_by_id(user.entity_id)
    if not vendor:
        raise ForbiddenException("This endpoint requires a vendor account")
    # Defense in depth: a vendor active at login time may be blocked/rejected mid-session by
    # Super Admin before their existing access token expires — re-check on every request.
    if vendor.status != VendorStatus.ACTIVE:
        raise ForbiddenException(f"Portal access is not available — vendor account status is '{vendor.status.value}'")
    return vendor


def get_vendor_registration_service(session: Session = Depends(get_db)) -> VendorRegistrationService:
    return VendorRegistrationService(session)


def get_rfq_service(session: Session = Depends(get_db)) -> RfqService:
    return RfqService(session)


def get_quotation_service(session: Session = Depends(get_db)) -> QuotationService:
    return QuotationService(session)


def get_purchase_order_service(session: Session = Depends(get_db)) -> PurchaseOrderService:
    return PurchaseOrderService(session)


def get_asn_service(session: Session = Depends(get_db)) -> AsnService:
    return AsnService(session)


def get_shipment_service(session: Session = Depends(get_db)) -> ShipmentService:
    return ShipmentService(session)


def get_invoice_service(session: Session = Depends(get_db)):
    from app.services.vendor.invoice_service import InvoiceService

    return InvoiceService(session)


def get_payment_service(session: Session = Depends(get_db)) -> PaymentService:
    return PaymentService(session)


def get_freight_payment_service(session: Session = Depends(get_db)) -> FreightPaymentService:
    return FreightPaymentService(session)


def get_vendor_return_service(session: Session = Depends(get_db)) -> VendorReturnService:
    return VendorReturnService(session)


def get_goods_service(session: Session = Depends(get_db)) -> GoodsService:
    return GoodsService(session)


def get_catalog_service(session: Session = Depends(get_db)) -> CatalogService:
    return CatalogService(session)
