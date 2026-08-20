import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    read: bool
    created_at: datetime


class NotificationListMeta(BaseModel):
    unread_count: int
    muted: bool = False


class CreateNotificationRequest(BaseModel):
    title: str
    body: str | None = None
    roles: list[str]
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


class MuteRequest(BaseModel):
    role: str
    muted: bool
