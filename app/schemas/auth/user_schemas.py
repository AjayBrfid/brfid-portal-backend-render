import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str
    last_login_at: datetime | None = None
    status: str


class UserDetail(UserListItem):
    code: str
    designation: str | None = None
    phone: str | None = None
    created_at: datetime


class CreateUserRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    role: str
    country_code: str = "+91"
    phone: str
    temporary_password: str
    send_welcome_email: bool = True
    require_reset: bool = True


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    role: str | None = None


class UpdateStatusRequest(BaseModel):
    status: str  # 'active' | 'inactive'
