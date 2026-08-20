"""Shared user-management router, mounted once per portal (warehouse/vendor/retail — not
super_admin, which has no sub-admin user-creation flow of its own) inside that portal's own
router module. One implementation serves all three since the underlying shape is identical."""
from datetime import date

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal, require_role
from app.dependencies.user_management import get_user_management_service
from app.models.user import User
from app.schemas.auth.user_schemas import CreateUserRequest, UpdateStatusRequest, UpdateUserRequest, UserDetail, UserListItem
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.services.auth.user_management_service import UserManagementService

_ADMIN_ROLE_BY_PORTAL = {"warehouse": "wh-admin", "store": "store-admin", "vendor": "vendor-admin"}


def build_users_router(portal_type: str) -> APIRouter:
    router = APIRouter(prefix="/users", tags=[f"{portal_type}-users"])
    portal_dep = require_portal(portal_type)
    admin_dep = require_role(_ADMIN_ROLE_BY_PORTAL[portal_type])

    @router.get("", response_model=ApiResponse[list[UserListItem]])
    def list_users(
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        params: PaginationParams = Depends(),
        service: UserManagementService = Depends(get_user_management_service),
        user: User = Depends(portal_dep),
    ):
        items, total = service.list_users(portal_type, user.entity_id, params, search, role, status, date_from, date_to)
        return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))

    @router.post("", response_model=ApiResponse[UserDetail], status_code=201)
    def create_user(
        body: CreateUserRequest,
        service: UserManagementService = Depends(get_user_management_service),
        user: User = Depends(admin_dep),
    ):
        created = service.create_user(
            portal_type,
            user.entity_id,
            body.first_name,
            body.last_name,
            body.email,
            body.role,
            f"{body.country_code} {body.phone}",
            body.temporary_password,
        )
        return ApiResponse(data=created)

    @router.get("/{user_id}", response_model=ApiResponse[UserDetail])
    def get_user(
        user_id: str, service: UserManagementService = Depends(get_user_management_service), user: User = Depends(portal_dep)
    ):
        return ApiResponse(data=service.get_user(portal_type, user.entity_id, user_id))

    @router.patch("/{user_id}", response_model=ApiResponse[UserDetail])
    def update_user(
        user_id: str,
        body: UpdateUserRequest,
        service: UserManagementService = Depends(get_user_management_service),
        user: User = Depends(admin_dep),
    ):
        return ApiResponse(data=service.update_user(portal_type, user.entity_id, user_id, **body.model_dump()))

    @router.patch("/{user_id}/status", response_model=ApiResponse[UserDetail])
    def update_status(
        user_id: str,
        body: UpdateStatusRequest,
        service: UserManagementService = Depends(get_user_management_service),
        user: User = Depends(admin_dep),
    ):
        return ApiResponse(data=service.update_status(portal_type, user.entity_id, user_id, body.status, user))

    @router.post("/{user_id}/reset-password", response_model=ApiResponse[dict])
    def reset_password(
        user_id: str,
        service: UserManagementService = Depends(get_user_management_service),
        user: User = Depends(admin_dep),
    ):
        service.trigger_password_reset(portal_type, user.entity_id, user_id)
        return ApiResponse(data={})

    return router
