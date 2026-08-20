from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies.auth import get_current_user
from app.dependencies.vendor import get_asn_service, get_current_vendor
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import CreateAsnRequest, ResubmitAsnRequest
from app.services.vendor.asn_service import AsnService
from app.utils.storage import get_storage_client

router = APIRouter(prefix="/asn", tags=["vendor-asn"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_asns(params: PaginationParams = Depends(), service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{asn_id}", response_model=ApiResponse[dict])
def get_asn(asn_id: str, service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.get_detail_for_vendor(vendor.id, asn_id))


@router.post("/purchase-orders/{po_id}", response_model=ApiResponse[dict], status_code=201)
def create_asn(po_id: str, body: CreateAsnRequest, service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor)):
    asn = service.create_asn(vendor.id, po_id, body.shipped_qty, body.expected_delivery_date, body.transport_charge)
    return ApiResponse(data=service.get_detail(asn.id))


@router.put("/{asn_id}/submit", response_model=ApiResponse[dict])
def submit_asn(
    asn_id: str, service: AsnService = Depends(get_asn_service),
    vendor: Vendor = Depends(get_current_vendor), user: User = Depends(get_current_user),
):
    asn = service.submit_asn(vendor.id, asn_id, user.id)
    return ApiResponse(data=service.get_detail(asn.id))


@router.put("/{asn_id}/resubmit", response_model=ApiResponse[dict])
def resubmit_asn(asn_id: str, body: ResubmitAsnRequest, service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor)):
    asn = service.resubmit_after_rejection(vendor.id, asn_id, body.shipped_qty, body.expected_delivery_date, body.batch_no)
    return ApiResponse(data=service.get_detail(asn.id))


@router.post("/{asn_id}/attachments", response_model=ApiResponse[dict], status_code=201)
def upload_asn_attachment(asn_id: str, remark: str | None = Form(None), file: UploadFile = File(...), service: AsnService = Depends(get_asn_service), vendor: Vendor = Depends(get_current_vendor)):
    service._get_asn_for_vendor(vendor.id, asn_id)  # 404s if this ASN isn't this vendor's
    uploaded = get_storage_client().save(file, folder="asn-attachments")
    attachment = service.upload_attachment(asn_id, uploaded.name, uploaded.url, remark, "vendor")
    return ApiResponse(data={"id": attachment.id, "file_name": attachment.file_name, "url": attachment.url})
