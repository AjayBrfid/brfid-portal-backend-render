from fastapi import APIRouter, Depends

from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.vendor import get_vendor_return_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import VendorReturnDispatchRequest, VendorReturnPickupRequest, VendorReturnReviewRequest
from app.services.vendor.vendor_return_service import VendorReturnService

router = APIRouter(prefix="/returns/vendor", tags=["warehouse-vendor-returns"])
_portal = require_portal("warehouse")


@router.get("", response_model=ApiResponse[list[dict]])
def list_returns(status: str | None = None, params: PaginationParams = Depends(), service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    items, total = service.list_for_warehouse(user.entity_id, params, status)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{return_id}", response_model=ApiResponse[dict])
def get_return(return_id: str, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_for_warehouse(user.entity_id, return_id))


@router.get("/{return_id}/attachments/{attachment_id}")
def get_return_attachment(return_id: str, attachment_id: str, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    row = service.repo.get_for_warehouse(user.entity_id, return_id)
    if not row:
        raise NotFoundException("Vendor return not found")
    attachment = service.repo.get_attachment(return_id, attachment_id)
    if not attachment:
        raise NotFoundException("Attachment not found")
    from app.compat.vendor.common import redirect_to_file

    return redirect_to_file(attachment.url)


@router.post("/{return_id}/approve", response_model=ApiResponse[dict])
def approve_return(return_id: str, body: VendorReturnReviewRequest, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.approve(user.entity_id, return_id, body.remarks, body.refund_amount))


@router.post("/{return_id}/reject", response_model=ApiResponse[dict])
def reject_return(return_id: str, body: VendorReturnReviewRequest, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.reject(user.entity_id, return_id, body.remarks))


@router.post("/{return_id}/pickup", response_model=ApiResponse[dict])
def schedule_pickup(return_id: str, body: VendorReturnPickupRequest, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.schedule_pickup(user.entity_id, return_id, body.pickup_date, body.transporter, body.vehicle_no))


@router.post("/{return_id}/dispatch", response_model=ApiResponse[dict])
def dispatch_return(return_id: str, body: VendorReturnDispatchRequest, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.dispatch(user.entity_id, return_id, body.tracking_no))


@router.post("/{return_id}/mark-delivered", response_model=ApiResponse[dict])
def mark_delivered(return_id: str, service: VendorReturnService = Depends(get_vendor_return_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.mark_delivered(user.entity_id, return_id))
