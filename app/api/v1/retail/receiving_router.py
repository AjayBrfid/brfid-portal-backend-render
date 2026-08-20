from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_receiving_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.retail.retail_schemas import RaiseIssueRequest, RecordCountRequest
from app.services.retail.receiving_service import ReceivingService

router = APIRouter(prefix="/receiving", tags=["retail-receiving"])
_portal = require_portal("store")


@router.get("", response_model=ApiResponse[list[dict]])
def list_receiving(service: ReceivingService = Depends(get_receiving_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_receiving(user.entity_id))


@router.get("/write-offs", response_model=ApiResponse[list[dict]])
def list_write_offs(period: str = "weekly", service: ReceivingService = Depends(get_receiving_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_write_offs(user.entity_id, period))


@router.put("/{item_id}", response_model=ApiResponse[dict])
def record_count(item_id: str, body: RecordCountRequest, service: ReceivingService = Depends(get_receiving_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.record_count(user.entity_id, item_id, body.received, body.condition, user.id))


@router.post("/{item_id}/issue", response_model=ApiResponse[dict])
def raise_issue(item_id: str, body: RaiseIssueRequest, service: ReceivingService = Depends(get_receiving_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.raise_issue(user.entity_id, item_id, body.issue_type, body.issue_qty, body.issue_note, body.return_type, user.id))
