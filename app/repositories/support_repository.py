from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.support import SupportRoutingRule, SupportTicket, SupportTicketAttachment, SupportTicketMessage
from app.schemas.common import PaginationParams
from app.utils.pagination import paginate


class SupportRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, ticket: SupportTicket) -> SupportTicket:
        self.session.add(ticket)
        self.session.flush()
        return ticket

    def get(self, ticket_id: uuid.UUID) -> SupportTicket | None:
        return self.session.get(SupportTicket, ticket_id)

    def list(
        self, params: PaginationParams, *, org_id: uuid.UUID | None = None, status: str | None = None,
        category: str | None = None, priority: str | None = None, role: str | None = None,
        sla_breached: bool | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
    ):
        stmt = select(SupportTicket)
        if org_id is not None:
            stmt = stmt.where(SupportTicket.raised_by_org_id == org_id)
        if status:
            stmt = stmt.where(SupportTicket.status == status)
        if category:
            stmt = stmt.where(SupportTicket.category == category)
        if priority:
            stmt = stmt.where(SupportTicket.priority == priority)
        if role:
            stmt = stmt.where(SupportTicket.raised_by_role == role)
        if date_from:
            stmt = stmt.where(SupportTicket.created_at >= date_from)
        if date_to:
            stmt = stmt.where(SupportTicket.created_at < date_to)
        if sla_breached is not None:
            now = datetime.utcnow()
            if sla_breached:
                stmt = stmt.where(SupportTicket.sla_due_at < now, SupportTicket.status.in_(["open", "in_progress"]))
            else:
                stmt = stmt.where((SupportTicket.sla_due_at >= now) | (~SupportTicket.status.in_(["open", "in_progress"])))
        stmt = stmt.order_by(SupportTicket.created_at.desc())
        return paginate(self.session, stmt, params)

    def add_message(self, message: SupportTicketMessage) -> SupportTicketMessage:
        self.session.add(message)
        self.session.flush()
        return message

    def list_messages(self, ticket_id: uuid.UUID, *, include_internal: bool) -> list[SupportTicketMessage]:
        stmt = select(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket_id)
        if not include_internal:
            stmt = stmt.where(SupportTicketMessage.is_internal_note.is_(False))
        stmt = stmt.order_by(SupportTicketMessage.created_at.asc())
        return list(self.session.scalars(stmt))

    def add_attachment(self, attachment: SupportTicketAttachment) -> SupportTicketAttachment:
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def list_attachments(self, ticket_id: uuid.UUID) -> list[SupportTicketAttachment]:
        stmt = select(SupportTicketAttachment).where(SupportTicketAttachment.ticket_id == ticket_id)
        return list(self.session.scalars(stmt))

    def get_routing_rule(self, category: str) -> SupportRoutingRule | None:
        return self.session.scalar(select(SupportRoutingRule).where(SupportRoutingRule.category == category))

    def list_routing_rules(self) -> list[SupportRoutingRule]:
        return list(self.session.scalars(select(SupportRoutingRule).order_by(SupportRoutingRule.category)))

    def add_routing_rule(self, rule: SupportRoutingRule) -> SupportRoutingRule:
        self.session.add(rule)
        self.session.flush()
        return rule

    def get_routing_rule_by_id(self, rule_id: uuid.UUID) -> SupportRoutingRule | None:
        return self.session.get(SupportRoutingRule, rule_id)

    def list_resolved_before(self, cutoff: datetime) -> list[SupportTicket]:
        stmt = select(SupportTicket).where(SupportTicket.status == "resolved", SupportTicket.resolved_at < cutoff)
        return list(self.session.scalars(stmt))

    def list_sla_breached_open(self) -> list[SupportTicket]:
        now = datetime.utcnow()
        stmt = select(SupportTicket).where(
            SupportTicket.status.in_(["open", "in_progress"]), SupportTicket.sla_due_at < now
        )
        return list(self.session.scalars(stmt))
