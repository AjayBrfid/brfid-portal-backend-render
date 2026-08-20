from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies.vendor import get_current_vendor, get_vendor_registration_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse
from app.schemas.vendor.vendor_schemas import UpdateVendorProfileRequest, VendorRegistrationRequest
from app.services.vendor.vendor_service import VendorRegistrationService

router = APIRouter(tags=["vendor-registration"])


@router.post("/registration", response_model=ApiResponse[dict], status_code=201)
def register(body: VendorRegistrationRequest, service: VendorRegistrationService = Depends(get_vendor_registration_service)):
    vendor = service.register(
        body.name, body.contact_person, body.contact_email, body.contact_phone, body.state, body.city,
        body.address, body.gst, body.pan, body.admin_email, body.temporary_password, body.category,
    )
    return ApiResponse(data={"vendor_id": vendor.id, "status": vendor.status.value})


@router.get("/profile", response_model=ApiResponse[dict])
def get_profile(vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data={"id": vendor.id, "code": vendor.code, "name": vendor.name, "status": vendor.status.value, "gst": vendor.gst, "pan": vendor.pan})


@router.patch("/profile", response_model=ApiResponse[dict])
def update_profile(body: UpdateVendorProfileRequest, vendor: Vendor = Depends(get_current_vendor), service: VendorRegistrationService = Depends(get_vendor_registration_service)):
    updated = service.update_profile(vendor.id, **body.model_dump())
    return ApiResponse(data={"id": updated.id, "name": updated.name})


@router.post("/profile/documents", response_model=ApiResponse[dict], status_code=201)
def upload_document(
    doc_type: str = Form(...), file: UploadFile = File(...),
    vendor: Vendor = Depends(get_current_vendor), service: VendorRegistrationService = Depends(get_vendor_registration_service),
):
    doc = service.upload_document(vendor.id, doc_type, file)
    return ApiResponse(data={"id": doc.id, "doc_type": doc.doc_type.value, "url": doc.url})
