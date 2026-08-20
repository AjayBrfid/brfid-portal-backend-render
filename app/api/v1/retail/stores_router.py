"""Store self-registration + document upload — deliberately unauthenticated, matching
Backend-WH-Retail's original design (no real session exists yet during this window)."""
from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_store_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.retail.retail_schemas import RegisterStoreRequest, RegisterStoreResponse
from app.services.retail.store_service import StoreService
from app.utils.storage import UploadedFileOut

router = APIRouter(tags=["retail-stores"])
_portal = require_portal("store")


@router.post("/stores/register", response_model=ApiResponse[RegisterStoreResponse], status_code=201)
def register(body: RegisterStoreRequest, service: StoreService = Depends(get_store_service)):
    store = service.register_store(
        body.business_type, body.store_name, body.pan, body.gstin, body.cin, body.years_in_operation,
        body.admin_name, f"{body.country_code} {body.phone}", body.email, body.address, body.city, body.state,
        body.pincode, body.temporary_password, body.store_type,
    )
    return ApiResponse(data=RegisterStoreResponse(store_id=store.id, status=store.status.value.lower().replace(" ", "_")))


@router.post("/stores/{store_id}/documents", response_model=ApiResponse[UploadedFileOut], status_code=201)
def upload_document(store_id: str, doc_type: str = Form(...), file: UploadFile = File(...), service: StoreService = Depends(get_store_service)):
    return ApiResponse(data=service.upload_store_document(store_id, doc_type, file))


@router.get("/warehouses", response_model=ApiResponse[list[dict]])
def list_linked_warehouses(service: StoreService = Depends(get_store_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_linked_warehouses(user.entity_id))
