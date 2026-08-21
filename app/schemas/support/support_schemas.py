import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateTicketRequest(BaseModel):
    category: str
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    priority: str = "medium"


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to_user_id: uuid.UUID | None = None


class AddMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    is_internal_note: bool = False


class RoutingRuleRequest(BaseModel):
    category: str
    default_assignee_user_id: uuid.UUID | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_number: str
    raised_by_user_id: uuid.UUID
    raised_by_role: str
    raised_by_org_id: uuid.UUID | None
    category: str
    subject: str
    description: str
    priority: str
    status: str
    assigned_to_user_id: uuid.UUID | None
    sla_due_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    email_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TicketMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_user_id: uuid.UUID
    sender_role: str
    message: str
    is_internal_note: bool
    created_at: datetime


class TicketAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    message_id: uuid.UUID | None
    file_url: str
    file_name: str
    file_type: str
    file_size: int
    created_at: datetime


class TicketDetailOut(BaseModel):
    ticket: TicketOut
    messages: list[TicketMessageOut]
    attachments: list[TicketAttachmentOut]


class RoutingRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    default_assignee_user_id: uuid.UUID | None
