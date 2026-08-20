from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.retail.dashboard_service import RetailDashboardService
from app.services.retail.product_service import ProductService
from app.services.retail.purchase_request_service import RetailPurchaseRequestService
from app.services.retail.receiving_service import ReceivingService
from app.services.retail.reports_service import RetailReportsService
from app.services.retail.store_return_service import StoreReturnService
from app.services.retail.store_service import StoreService
from app.services.retail.store_settings_service import StoreSettingsService


def get_store_service(session: Session = Depends(get_db)) -> StoreService:
    return StoreService(session)


def get_store_settings_service(session: Session = Depends(get_db)) -> StoreSettingsService:
    return StoreSettingsService(session)


def get_product_service(session: Session = Depends(get_db)) -> ProductService:
    return ProductService(session)


def get_receiving_service(session: Session = Depends(get_db)) -> ReceivingService:
    return ReceivingService(session)


def get_retail_store_return_service(session: Session = Depends(get_db)) -> StoreReturnService:
    return StoreReturnService(session)


def get_retail_purchase_request_service(session: Session = Depends(get_db)) -> RetailPurchaseRequestService:
    return RetailPurchaseRequestService(session)


def get_retail_dashboard_service(session: Session = Depends(get_db)) -> RetailDashboardService:
    return RetailDashboardService(session)


def get_retail_reports_service(session: Session = Depends(get_db)) -> RetailReportsService:
    return RetailReportsService(session)
