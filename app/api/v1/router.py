from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.retail.router import router as retail_router
from app.api.v1.super_admin.router import router as super_admin_router
from app.api.v1.support.router import router as support_router
from app.api.v1.vendor.router import router as vendor_router
from app.api.v1.warehouse.router import router as warehouse_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(super_admin_router)
api_router.include_router(vendor_router)
api_router.include_router(warehouse_router)
api_router.include_router(retail_router)
api_router.include_router(support_router)
