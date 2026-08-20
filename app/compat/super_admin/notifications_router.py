"""vms-sa-react's Notifications view (`/notifications...`). mark-read/mark-all-read/unread-count
call straight through to NotificationService — the same service every portal's real
notifications router already uses (see app/api/v1/auth/notifications_router.py) — just under the
old contract's verbs/paths (PUT instead of PATCH for mark-read) and field names (`text`/`unread`
instead of `body`/`read`). The list endpoint's `type` filter isn't supported by
NotificationRepository.list_for_user, so it queries Notification directly rather than extending
that shared method's signature for one caller."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import NotificationOut
from app.dependencies.auth import require_portal
from app.dependencies.notification import get_notification_service
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams
from app.services.auth.notification_service import NotificationService
from app.utils.pagination import paginate

router = APIRouter(prefix="/notifications", tags=["super-admin-compat-notifications"])
_portal = require_portal("super_admin")


def _to_out(n: Notification) -> dict:
    return {"id": n.id, "type": n.type, "title": n.title, "text": n.body, "created_at": n.created_at, "unread": not n.read}


@router.get("", response_model=ApiResponse[list[NotificationOut]])
def list_notifications(
    type: str | None = None, params: PaginationParams = Depends(),
    service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal),
):
    stmt = select(Notification).where(Notification.recipient_user_id == user.id)
    if type:
        stmt = stmt.where(Notification.type == type)
    stmt = stmt.order_by(Notification.created_at.desc())
    rows, total = paginate(service.session, stmt, params)
    return ApiResponse(data=[_to_out(n) for n in rows], meta=admin_meta(params.page, params.limit, total))


@router.get("/unread-count", response_model=ApiResponse[dict])
def unread_count(service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal)):
    return ApiResponse(data={"count": service.repo.unread_count(user.id)})


@router.put("/{notification_id}/read", response_model=ApiResponse[dict])
def mark_read(notification_id: uuid.UUID, service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal)):
    service.mark_read(user.id, notification_id)
    return ApiResponse(data={})


@router.post("/read-all", response_model=ApiResponse[dict])
def mark_all_read(service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal)):
    service.mark_all_read(user.id, None)
    return ApiResponse(data={})
