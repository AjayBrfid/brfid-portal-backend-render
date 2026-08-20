from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.warehouse.dashboard_service import WarehouseDashboardService
from app.services.warehouse.inventory_service import InventoryService
from app.services.warehouse.purchase_request_service import PurchaseRequestService
from app.services.warehouse.reports_service import WarehouseReportsService
from app.services.warehouse.store_return_service import WarehouseStoreReturnService
from app.services.warehouse.transfer_order_service import TransferOrderService
from app.services.warehouse.warehouse_service import WarehouseService


def get_warehouse_service(session: Session = Depends(get_db)) -> WarehouseService:
    return WarehouseService(session)


def get_inventory_service(session: Session = Depends(get_db)) -> InventoryService:
    return InventoryService(session)


def get_purchase_request_service(session: Session = Depends(get_db)) -> PurchaseRequestService:
    return PurchaseRequestService(session)


def get_transfer_order_service(session: Session = Depends(get_db)) -> TransferOrderService:
    return TransferOrderService(session)


def get_warehouse_store_return_service(session: Session = Depends(get_db)) -> WarehouseStoreReturnService:
    return WarehouseStoreReturnService(session)


def get_warehouse_dashboard_service(session: Session = Depends(get_db)) -> WarehouseDashboardService:
    return WarehouseDashboardService(session)


def get_warehouse_reports_service(session: Session = Depends(get_db)) -> WarehouseReportsService:
    return WarehouseReportsService(session)
