"""Shared notifications router, mounted once per portal inside that portal's own router
module. Retail (portal_type "store") gains two extra routes — the coarse per-role mute switch
and the Employee -> Manager "Alert Manager" broadcast — neither of which applies elsewhere."""
import uuid

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.notification import get_notification_service
from app.models.user import User
from app.schemas.auth.notification_schemas import CreateNotificationRequest, MuteRequest, NotificationOut
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.auth.notification_service import NotificationService


def build_notifications_router(portal_type: str) -> APIRouter:
    router = APIRouter(prefix="/notifications", tags=[f"{portal_type}-notifications"])
    portal_dep = require_portal(portal_type)

    @router.get("", response_model=ApiResponse[list[NotificationOut]])
    def list_notifications(
        read: bool | None = None,
        params: PaginationParams = Depends(),
        service: NotificationService = Depends(get_notification_service),
        user: User = Depends(portal_dep),
    ):
        items, total, unread_count = service.list_for_user(user.id, params, read)
        meta = build_meta(params.page, params.limit, total)
        meta["unreadCount"] = unread_count
        if portal_type == "store":
            meta["muted"] = service.is_muted(user.entity_id, user.role)
        return ApiResponse(data=items, meta=meta)

    @router.patch("/{notification_id}/read", response_model=ApiResponse[NotificationOut])
    def mark_read(
        notification_id: uuid.UUID,
        service: NotificationService = Depends(get_notification_service),
        user: User = Depends(portal_dep),
    ):
        return ApiResponse(data=service.mark_read(user.id, notification_id))

    @router.post("/read-all", response_model=ApiResponse[dict])
    def mark_all_read(
        type: str | None = None,
        service: NotificationService = Depends(get_notification_service),
        user: User = Depends(portal_dep),
    ):
        service.mark_all_read(user.id, type)
        return ApiResponse(data={})

    if portal_type == "store":

        @router.put("/mute", response_model=ApiResponse[dict])
        def mute(
            body: MuteRequest, service: NotificationService = Depends(get_notification_service), user: User = Depends(portal_dep)
        ):
            service.set_muted(user.entity_id, body.role, body.muted)
            return ApiResponse(data={})

        @router.post("", response_model=ApiResponse[list[NotificationOut]], status_code=201)
        def create_alert(
            body: CreateNotificationRequest,
            service: NotificationService = Depends(get_notification_service),
            user: User = Depends(portal_dep),
        ):
            created = service.create_for_roles(
                portal_type,
                user.entity_id,
                body.roles,
                body.title,
                body.body,
                "employee-alert",
                body.entity_type,
                body.entity_id,
            )
            return ApiResponse(data=created)

    return router
