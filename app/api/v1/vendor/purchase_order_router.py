from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_purchase_order_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import PoRejectRequest
from app.services.vendor.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["vendor-purchase-orders"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_purchase_orders(status: str | None = None, params: PaginationParams = Depends(), service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{po_id}", response_model=ApiResponse[dict])
def get_purchase_order(po_id: str, service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.get_detail_for_vendor(vendor.id, po_id))


@router.patch("/{po_id}/accept", response_model=ApiResponse[dict])
def accept_purchase_order(po_id: str, service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.accept(vendor.id, po_id))


@router.patch("/{po_id}/reject", response_model=ApiResponse[dict])
def reject_purchase_order(po_id: str, body: PoRejectRequest, service: PurchaseOrderService = Depends(get_purchase_order_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.reject(vendor.id, po_id, body.reason))
