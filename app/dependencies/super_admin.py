from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.super_admin.store_admin_service import AdminStoreService
from app.services.super_admin.vendor_admin_service import AdminVendorService
from app.services.super_admin.warehouse_admin_service import AdminWarehouseService


def get_admin_warehouse_service(session: Session = Depends(get_db)) -> AdminWarehouseService:
    return AdminWarehouseService(session)


def get_admin_store_service(session: Session = Depends(get_db)) -> AdminStoreService:
    return AdminStoreService(session)


def get_admin_vendor_service(session: Session = Depends(get_db)) -> AdminVendorService:
    return AdminVendorService(session)
