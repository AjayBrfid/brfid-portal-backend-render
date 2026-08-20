from fastapi import APIRouter, Depends, File, UploadFile

from app.dependencies.auth import require_portal
from app.dependencies.vendor import get_asn_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import GoodsReceiptRequest
from app.services.vendor.asn_service import AsnService
from app.utils.storage import get_storage_client

router = APIRouter(prefix="/purchase-orders/{po_id}/asns", tags=["warehouse-asn"])
_portal = require_portal("warehouse")


@router.post("/{asn_id}/rejection-attachments", response_model=ApiResponse[dict])
def upload_rejection_attachment(po_id: str, asn_id: str, file: UploadFile = File(...), _: User = Depends(_portal)):
    # Uploaded before the inspect call (the VendorReturn this attaches to doesn't exist until
    # inspect creates it) so the resulting {fileName, url} can be included in that request body.
    uploaded = get_storage_client().save(file, folder="vendor-return-attachments")
    return ApiResponse(data={"fileName": uploaded.name, "url": uploaded.url})


@router.get("", response_model=ApiResponse[list[dict]])
def list_asns(po_id: str, params: PaginationParams = Depends(), service: AsnService = Depends(get_asn_service), user: User = Depends(_portal)):
    items, total = service.list_for_warehouse(user.entity_id, params, po_id)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.post("/{asn_id}/inspect", response_model=ApiResponse[dict])
def inspect_asn(po_id: str, asn_id: str, body: GoodsReceiptRequest, service: AsnService = Depends(get_asn_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.record_goods_receipt(
        user.entity_id, po_id, asn_id, body.accepted_qty, body.rejected_qty, body.rejection_reason,
        user_id=user.id, attachments=body.attachments,
    ))
