import io
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.constants.roles import SUPPORT_STAFF_ROLES
from app.constants.support import CATEGORIES_BY_ROLE
from app.dependencies.auth import get_current_user, require_role
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.support.support_schemas import (
    AddMessageRequest,
    CreateTicketRequest,
    RoutingRuleOut,
    RoutingRuleRequest,
    TicketAttachmentOut,
    TicketDetailOut,
    TicketMessageOut,
    TicketOut,
    UpdateTicketRequest,
)
from app.services.support.support_service import SupportService

router = APIRouter(prefix="/support", tags=["support"])
_staff = require_role(*SUPPORT_STAFF_ROLES)


@router.get("/categories", response_model=ApiResponse[list[str]])
def get_categories(user: User = Depends(get_current_user)):
    return ApiResponse(data=CATEGORIES_BY_ROLE.get(user.portal_type.value, []))


@router.post("/tickets", response_model=ApiResponse[TicketOut])
def create_ticket(
    body: CreateTicketRequest, session: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    service = SupportService(session)
    ticket = service.create_ticket(user, body.category, body.subject, body.description, body.priority)
    return ApiResponse(data=TicketOut.model_validate(ticket))


@router.get("/tickets", response_model=ApiResponse[list[TicketOut]])
def list_tickets(
    status: str | None = None, category: str | None = None, priority: str | None = None,
    role: str | None = None, sla_breached: bool | None = None,
    date_from: date | None = None, date_to: date | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    service = SupportService(session)
    date_from_dt = datetime.combine(date_from, datetime.min.time()) if date_from else None
    date_to_dt = datetime.combine(date_to, datetime.min.time()) if date_to else None
    rows, total = service.list_tickets(
        user, params, status=status, category=category, priority=priority, role=role,
        sla_breached=sla_breached, date_from=date_from_dt, date_to=date_to_dt,
    )
    return ApiResponse(data=[TicketOut.model_validate(r) for r in rows], meta=build_meta(params.page, params.limit, total))


@router.get("/tickets/export")
def export_tickets(
    status: str | None = None, category: str | None = None, priority: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    session: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    service = SupportService(session)
    date_from_dt = datetime.combine(date_from, datetime.min.time()) if date_from else None
    date_to_dt = datetime.combine(date_to, datetime.min.time()) if date_to else None
    big_page = PaginationParams(page=1, limit=5000)
    rows, _ = service.list_tickets(
        user, big_page, status=status, category=category, priority=priority,
        date_from=date_from_dt, date_to=date_to_dt,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Support Tickets"
    headers = ["Ticket #", "Category", "Subject", "Priority", "Status", "Raised By Role", "Created At", "SLA Due", "Resolved At"]
    ws.append(headers)
    for t in rows:
        ws.append([
            t.ticket_number, t.category, t.subject, t.priority, t.status, t.raised_by_role,
            t.created_at.replace(tzinfo=None) if t.created_at else None,
            t.sla_due_at.replace(tzinfo=None) if t.sla_due_at else None,
            t.resolved_at.replace(tzinfo=None) if t.resolved_at else None,
        ])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=support_tickets.xlsx"},
    )


@router.get("/tickets/{ticket_id}", response_model=ApiResponse[TicketDetailOut])
def get_ticket(ticket_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service = SupportService(session)
    ticket, messages, attachments = service.get_detail(user, ticket_id)
    return ApiResponse(data=TicketDetailOut(
        ticket=TicketOut.model_validate(ticket),
        messages=[TicketMessageOut.model_validate(m) for m in messages],
        attachments=[TicketAttachmentOut.model_validate(a) for a in attachments],
    ))


@router.patch("/tickets/{ticket_id}", response_model=ApiResponse[TicketOut])
def update_ticket(
    ticket_id: uuid.UUID, body: UpdateTicketRequest, session: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    service = SupportService(session)
    ticket = service.update_ticket(user, ticket_id, body.status, body.priority, body.assigned_to_user_id)
    return ApiResponse(data=TicketOut.model_validate(ticket))


@router.post("/tickets/{ticket_id}/messages", response_model=ApiResponse[TicketMessageOut])
def add_message(
    ticket_id: uuid.UUID, body: AddMessageRequest, session: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    service = SupportService(session)
    message = service.add_message(user, ticket_id, body.message, body.is_internal_note)
    return ApiResponse(data=TicketMessageOut.model_validate(message))


@router.post("/tickets/{ticket_id}/attachments", response_model=ApiResponse[TicketAttachmentOut])
def add_attachment(
    ticket_id: uuid.UUID, file: UploadFile = File(...), message_id: uuid.UUID | None = Query(None),
    session: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    service = SupportService(session)
    attachment = service.add_attachment(user, ticket_id, file, message_id)
    return ApiResponse(data=TicketAttachmentOut.model_validate(attachment))


@router.get("/routing-rules", response_model=ApiResponse[list[RoutingRuleOut]])
def list_routing_rules(session: Session = Depends(get_db), _: User = Depends(_staff)):
    service = SupportService(session)
    return ApiResponse(data=[RoutingRuleOut.model_validate(r) for r in service.list_routing_rules()])


@router.post("/routing-rules", response_model=ApiResponse[RoutingRuleOut])
def upsert_routing_rule(body: RoutingRuleRequest, session: Session = Depends(get_db), _: User = Depends(_staff)):
    service = SupportService(session)
    rule = service.upsert_routing_rule(body.category, body.default_assignee_user_id)
    return ApiResponse(data=RoutingRuleOut.model_validate(rule))
