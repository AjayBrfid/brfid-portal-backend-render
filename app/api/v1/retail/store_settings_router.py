from fastapi import APIRouter, Depends, Response

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_store_settings_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.retail.retail_schemas import ApprovalOut, UpdateOrganizationRequest, UpdateThresholdRequest
from app.services.retail.store_settings_service import StoreSettingsService

router = APIRouter(prefix="/store", tags=["retail-store-settings"])
_portal = require_portal("store")


@router.get("", response_model=ApiResponse[dict])
def get_store(service: StoreSettingsService = Depends(get_store_settings_service), user: User = Depends(_portal)):
    store = service.get_store(user.entity_id)
    return ApiResponse(data={"id": store.id, "code": store.code, "name": store.name, "gstin": store.gstin, "address": store.address, "low_stock_threshold": store.low_stock_threshold})


@router.put("/organization", response_model=ApiResponse[dict] | None)
def update_organization(body: UpdateOrganizationRequest, response: Response, service: StoreSettingsService = Depends(get_store_settings_service), user: User = Depends(_portal)):
    result = service.update_organization(user.entity_id, user.id, user.role, body.name, body.gstin, body.address)
    if result is None:
        response.status_code = 204
        return None
    return ApiResponse(data=result)


@router.put("/low-stock-threshold", response_model=ApiResponse[dict] | None)
def update_threshold(body: UpdateThresholdRequest, response: Response, service: StoreSettingsService = Depends(get_store_settings_service), user: User = Depends(_portal)):
    result = service.update_low_stock_threshold(user.entity_id, user.id, user.role, body.threshold)
    if result is None:
        response.status_code = 204
        return None
    return ApiResponse(data=result)


@router.get("/approvals/{approval_id}", response_model=ApiResponse[ApprovalOut])
def get_approval(approval_id: str, service: StoreSettingsService = Depends(get_store_settings_service), _: User = Depends(_portal)):
    approval = service.get_approval(approval_id)
    return ApiResponse(data=ApprovalOut(id=approval.id, status=approval.status.value))


@router.post("/approvals/{approval_id}/approve", status_code=204)
def approve(approval_id: str, service: StoreSettingsService = Depends(get_store_settings_service), user: User = Depends(_portal)):
    service.approve(approval_id, user.id)
