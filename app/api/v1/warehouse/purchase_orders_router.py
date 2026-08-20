from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.vendor import get_invoice_service, get_purchase_order_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.vendor.invoice_service import InvoiceService
from app.services.vendor.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["warehouse-purchase-orders"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_pos(search: str | None = None, status: str | None = None, params: PaginationParams = Depends(), service: PurchaseOrderService = Depends(get_purchase_order_service), user: User = Depends(_portal)):
    items, total = service.list_for_warehouse(user.entity_id, params, search, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{po_id}", response_model=ApiResponse[dict])
def get_po(po_id: str, service: PurchaseOrderService = Depends(get_purchase_order_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_detail_for_warehouse(user.entity_id, po_id))


@router.get("/{po_id}/invoices", response_model=ApiResponse[list[dict]])
def list_invoices(po_id: str, params: PaginationParams = Depends(), invoice_service: InvoiceService = Depends(get_invoice_service), user: User = Depends(_portal)):
    items, total = invoice_service.list_for_warehouse(user.entity_id, params, po_id=po_id)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))
