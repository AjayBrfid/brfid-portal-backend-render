"""The one genuinely missing piece of vms-sa-react's old auth contract — everything else
(login, logout, /me) is already handled directly in app/api/v1/auth/router.py. Reuses
AuthService.change_password (the exact same logic /auth/me/change-password already calls in the
new contract) — just a different URL/verb/body-casing to match the old frontend."""
from fastapi import APIRouter, Depends

from app.compat.super_admin.schemas import ChangePasswordBody
from app.dependencies.auth import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.auth.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["super-admin-compat-auth"])


@router.put("/password", response_model=ApiResponse[dict])
def change_password(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    service.change_password(user, body.current_password, body.new_password)
    return ApiResponse(data={})
