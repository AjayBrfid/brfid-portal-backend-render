"""vms-sa-react's Activities feed (`/activities`) — genuinely new. Derived from the existing
cross-portal AuditLog table (see app/services/audit_service.py), reshaped into the old contract's
`{id, icon, text, createdAt}` shape. `icon` is inferred from the action_type prefix
(VENDOR_/WAREHOUSE_/STORE_/SKU -> vendor/warehouse/store/product); `text` is the audit
description as-is — the old contract's sample text embeds `<strong>` markup around entity names,
which this codebase's plain-text audit descriptions don't carry, so this is a plain-text
approximation, not a byte-for-byte match (noted in the implementation report)."""
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import ActivityOut
from app.dependencies.audit import get_audit_service
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams
from app.services.audit_service import AuditService
from app.utils.date_range import resolve_report_date_range
from app.utils.excel_export import build_activity_report_workbook
from app.utils.pagination import paginate

router = APIRouter(prefix="/activities", tags=["super-admin-compat-activities"])
_portal = require_portal("super_admin")

_ICON_PREFIXES = [
    ("VENDOR", "vendor"), ("WAREHOUSE", "warehouse"), ("STORE", "store"),
    ("SKU", "product"), ("RFQ", "rfq"), ("QUOTATION", "quotation"),
    ("PO", "po"), ("PURCHASE_ORDER", "po"),
]


def _icon_for(action_type: str) -> str:
    upper = action_type.upper()
    for prefix, icon in _ICON_PREFIXES:
        if upper.startswith(prefix):
            return icon
    return "activity"


@router.get("", response_model=ApiResponse[list[ActivityOut]])
def list_activities(
    search: str | None = None, params: PaginationParams = Depends(),
    session: Session = Depends(get_db), _: User = Depends(_portal),
):
    stmt = select(AuditLog)
    if search:
        stmt = stmt.where(AuditLog.description.ilike(f"%{search}%"))
    stmt = stmt.order_by(AuditLog.occurred_at.desc())
    rows, total = paginate(session, stmt, params)
    items = [{"id": r.id, "icon": _icon_for(r.action_type), "text": r.description, "created_at": r.occurred_at} for r in rows]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/export")
def export_activity_report(
    date: date | None = None, date_from: date | None = None, date_to: date | None = None,
    audit: AuditService = Depends(get_audit_service), _: User = Depends(_portal),
):
    start, end, period_label = resolve_report_date_range(date, date_from, date_to)
    rows = audit.rows_for_report(None, None, start, end)
    buffer = build_activity_report_workbook("Super Admin", None, period_label, rows)
    filename = f"activity_report_super_admin_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
