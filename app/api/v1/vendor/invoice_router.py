from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_invoice_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import InvoiceCreateRequest
from app.services.vendor.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["vendor-invoices"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_invoices(status: str | None = None, params: PaginationParams = Depends(), service: InvoiceService = Depends(get_invoice_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{invoice_id}", response_model=ApiResponse[dict])
def get_invoice(invoice_id: str, service: InvoiceService = Depends(get_invoice_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.to_out(service.get_for_vendor(vendor.id, invoice_id)))


@router.post("", response_model=ApiResponse[dict], status_code=201)
def create_invoice(body: InvoiceCreateRequest, service: InvoiceService = Depends(get_invoice_service), vendor: Vendor = Depends(get_current_vendor)):
    invoice = service.create_invoice(
        vendor.id, body.po_id, body.asn_id, body.invoice_number, body.invoice_date, body.due_date,
        body.base_amount, body.gst_amount, body.discount_amount, body.freight_amount,
    )
    return ApiResponse(data=service.to_out(invoice))
