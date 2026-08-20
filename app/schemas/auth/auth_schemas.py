import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import PortalType


class LoginRequest(BaseModel):
    # portal_type is optional here to stay backward compatible with vms-sa-react's original
    # super-admin-only backend, whose /auth/login never sent a portal_type field at all — see
    # the login() handler in app/api/v1/auth/router.py, which defaults to "super_admin" and
    # returns that old {token, user:{name,role}} shape when portal_type is absent.
    portal_type: PortalType | None = None
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    email: str
    role: str
    portal_type: str
    entity_id: uuid.UUID | None = None
    entity_name: str | None = None
    designation: str | None = None
    phone: str | None = None
    status: str
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class LogoutRequest(BaseModel):
    # Optional for the same reason as LoginRequest.portal_type — vms-sa-react's original
    # POST /auth/logout sends no body at all.
    refresh_token: str | None = None


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    portal_type: PortalType
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateMeRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class AccountSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: str
    timezone: str
    date_format: str
    dark_mode: bool


class AccountSettingsUpdate(BaseModel):
    language: str | None = None
    timezone: str | None = None
    date_format: str | None = None
    dark_mode: bool | None = None


class NotificationPrefsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notify_new_pr: bool
    notify_vendor_rfq_response: bool
    notify_store_return: bool
    notify_po_ready_for_inspection: bool
    notify_transfer_order_status_change: bool
    notify_daily_summary: bool


class NotificationPrefsUpdate(BaseModel):
    notify_new_pr: bool | None = None
    notify_vendor_rfq_response: bool | None = None
    notify_store_return: bool | None = None
    notify_po_ready_for_inspection: bool | None = None
    notify_transfer_order_status_change: bool | None = None
    notify_daily_summary: bool | None = None
