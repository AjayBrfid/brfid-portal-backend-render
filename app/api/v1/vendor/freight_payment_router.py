"""Vendor's read-only view of its own freight payments — the warehouse-side router
(app/api/v1/warehouse/freight_payments_router.py) owns marking one paid; this only lists/views."""
from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_freight_payment_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.vendor.payment_service import FreightPaymentService

router = APIRouter(prefix="/freight-payments", tags=["vendor-freight-payments"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_freight_payments(status: str | None = None, params: PaginationParams = Depends(), service: FreightPaymentService = Depends(get_freight_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{freight_payment_id}", response_model=ApiResponse[dict])
def get_freight_payment(freight_payment_id: str, service: FreightPaymentService = Depends(get_freight_payment_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.get_for_vendor(vendor.id, freight_payment_id))
