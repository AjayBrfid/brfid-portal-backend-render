"""Notifications compat. Reuses the exact same NotificationService already wired for the real
`/api/v1/vendor/notifications` routes (app/api/v1/auth/notifications_router.py's
build_notifications_router) -- only field names/shape differ: old contract wants `text`
(real: `body`) and `unread` (real: `read`, inverted), plus a `meta.unreadCount` (real:
`meta["unreadCount"]`, same key already).
"""
from fastapi import APIRouter, Depends

from app.compat.vendor.common import envelope, iso, vendor_meta
from app.dependencies.auth import require_portal
from app.dependencies.notification import get_notification_service
from app.models.user import User
from app.schemas.common import PaginationParams
from app.services.auth.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["vendor-compat-notifications"])
_portal = require_portal("vendor")


def _notification_out(n) -> dict:
    return {
        "id": str(n.id), "type": n.type, "title": n.title, "text": n.body,
        "createdAt": iso(n.created_at), "unread": not n.read,
    }


@router.get("")
def list_notifications(
    page: int = 1, limit: int = 20, unread: bool | None = None,
    service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal),
):
    read = (not unread) if unread is not None else None
    params = PaginationParams(page=page, limit=limit)
    items, total, unread_count = service.list_for_user(user.id, params, read)
    meta = vendor_meta(page, limit, total, unreadCount=unread_count)
    return envelope([_notification_out(n) for n in items], meta)


@router.patch("/{notification_id}/read")
def mark_read(notification_id: str, service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal)):
    row = service.mark_read(user.id, notification_id)
    return envelope(_notification_out(row))


@router.patch("/mark-all-read")
def mark_all_read(service: NotificationService = Depends(get_notification_service), user: User = Depends(_portal)):
    service.mark_all_read(user.id)
    return envelope({"updatedCount": 0})
