from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.vendor import get_invoice_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.vendor.vendor_schemas import InvoiceStatusUpdateRequest
from app.services.vendor.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["warehouse-invoices"])
_portal = require_portal("warehouse")


@router.patch("/{invoice_id}/status", response_model=ApiResponse[dict])
def update_invoice_status(invoice_id: str, body: InvoiceStatusUpdateRequest, service: InvoiceService = Depends(get_invoice_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.update_status(invoice_id, body.status))


@router.patch("/{invoice_id}/pay", response_model=ApiResponse[dict])
def mark_invoice_paid(invoice_id: str, service: InvoiceService = Depends(get_invoice_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.mark_paid(invoice_id))
