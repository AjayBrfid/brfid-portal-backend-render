"""Unified auth router shared by all four portals — one flat `/api/v1/auth/*` namespace, with
`portal_type` disambiguating login/forgot-password rather than a URL segment (Backend-WH-Retail's
original per-portal-mounted `/{portal}/auth/...` factory is retired in favor of this; see the
consolidation plan's API-shape note — an explicit breaking change for the existing Warehouse/
Retail frontends, which called `/warehouse/auth/login` / `/retail/auth/login` with no
`portal_type` field). Protected routes below (`/me`, etc.) act on whoever's token this is —
no portal restriction needed here, since there's no URL segment to guard against replay across;
`require_portal`/`require_role` still gate the portal-specific routers (super_admin/vendor/
warehouse/retail) elsewhere.
"""
from fastapi import APIRouter, Depends

from app.dependencies.auth import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth.auth_schemas import (
    AccountSettingsOut,
    AccountSettingsUpdate,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    NotificationPrefsOut,
    NotificationPrefsUpdate,
    RefreshRequest,
    RefreshResponse,
    ResetPasswordRequest,
    TokenResponse,
    UpdateMeRequest,
    UserOut,
)
from app.schemas.common import ApiResponse
from app.services.auth.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=None)
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    if body.portal_type is None:
        # vms-sa-react's original (pre-unification) super-admin-only backend never sent
        # portal_type at all — its /auth/login contract is {email,password} -> {token, user:
        # {name,role}}. Defaulting to super_admin here keeps that frontend working unmodified.
        access_token, _refresh_token, user = service.login("super_admin", body.email, body.password)
        return {"success": True, "data": {"token": access_token, "user": {"name": user.name, "role": user.role}}}
    access_token, refresh_token, user = service.login(body.portal_type, body.email, body.password)
    return ApiResponse(data=TokenResponse(access_token=access_token, refresh_token=refresh_token, user=user))


@router.post("/refresh", response_model=ApiResponse[RefreshResponse])
def refresh(body: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    return ApiResponse(data=RefreshResponse(access_token=service.refresh_access_token(body.refresh_token)))


@router.post("/logout", response_model=ApiResponse[MessageResponse])
def logout(
    body: LogoutRequest = LogoutRequest(), service: AuthService = Depends(get_auth_service), _: User = Depends(get_current_user)
):
    # vms-sa-react's original POST /auth/logout sends no body at all — refresh_token is
    # optional for exactly that reason; there's nothing to revoke server-side in that case
    # (that old contract never had a refresh-token flow to begin with).
    if body.refresh_token:
        service.revoke_refresh_token(body.refresh_token)
    return ApiResponse(data=MessageResponse(message="Logged out"))


@router.post("/forgot-password", response_model=ApiResponse[MessageResponse])
def forgot_password(body: ForgotPasswordRequest, service: AuthService = Depends(get_auth_service)):
    service.request_password_reset(body.portal_type, body.email)
    return ApiResponse(data=MessageResponse(message="If that account exists, a reset link has been sent."))


@router.post("/reset-password", response_model=ApiResponse[MessageResponse])
def reset_password(body: ResetPasswordRequest, service: AuthService = Depends(get_auth_service)):
    service.reset_password(body.token, body.new_password)
    return ApiResponse(data=MessageResponse(message="Password reset successfully. You can now sign in."))


@router.get("/me", response_model=ApiResponse[UserOut])
def get_me(user: User = Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    return ApiResponse(data=service.attach_entity_name(user))


@router.patch("/me", response_model=ApiResponse[UserOut])
def patch_me(
    body: UpdateMeRequest, user: User = Depends(get_current_user), service: AuthService = Depends(get_auth_service)
):
    return ApiResponse(data=service.update_me(user, body.name, body.phone, body.email))


@router.post("/me/change-password", response_model=ApiResponse[MessageResponse])
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    service.change_password(user, body.current_password, body.new_password)
    return ApiResponse(data=MessageResponse(message="Password changed successfully."))


@router.get("/me/account-settings", response_model=ApiResponse[AccountSettingsOut])
def get_account_settings(user: User = Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    return ApiResponse(data=service.get_or_create_account_settings(user.id))


@router.patch("/me/account-settings", response_model=ApiResponse[AccountSettingsOut])
def patch_account_settings(
    body: AccountSettingsUpdate,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return ApiResponse(data=service.update_account_settings(user.id, **body.model_dump()))


@router.get("/me/notification-prefs", response_model=ApiResponse[NotificationPrefsOut])
def get_notification_prefs(user: User = Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    return ApiResponse(data=service.get_or_create_notification_prefs(user.id))


@router.patch("/me/notification-prefs", response_model=ApiResponse[NotificationPrefsOut])
def patch_notification_prefs(
    body: NotificationPrefsUpdate,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return ApiResponse(data=service.update_notification_prefs(user.id, **body.model_dump()))
