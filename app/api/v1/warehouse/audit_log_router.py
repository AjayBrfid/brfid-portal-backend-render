import uuid
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies.audit import get_audit_service
from app.dependencies.auth import require_role
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit-log", tags=["warehouse-audit-log"])
_admin = require_role("wh-admin")


@router.get("", response_model=ApiResponse[list[dict]])
def list_audit_log(
    search: str | None = None, user_id: uuid.UUID | None = None, action_type: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    params: PaginationParams = Depends(), service: AuditService = Depends(get_audit_service), _: User = Depends(_admin),
):
    rows, total = service.search("warehouse", params, search, user_id, action_type, date_from, date_to)
    items = [
        {"id": r.id, "occurred_at": r.occurred_at, "user_id": r.user_id, "action_type": r.action_type, "description": r.description, "entity_type": r.entity_type, "entity_id": r.entity_id}
        for r in rows
    ]
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/export")
def export_audit_log(
    search: str | None = None, user_id: uuid.UUID | None = None, action_type: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    service: AuditService = Depends(get_audit_service), _: User = Depends(_admin),
):
    csv_text = service.export_csv("warehouse", search, user_id, action_type, date_from, date_to)
    return StreamingResponse(iter([csv_text]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit_log.csv"})
