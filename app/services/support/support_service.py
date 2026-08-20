"""Support ticketing. Creation is always immediate -- there is no Super Admin approval/gate:
`create_ticket` saves the row as `status=open` and fires the SUPPORT_EMAIL notification
unconditionally, before any staff has looked at it. Staff (super-admin / support-agent) only
get involved afterwards via reply/assign/resolve.
"""
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.constants.roles import SUPPORT_STAFF_ROLES
from app.constants.support import CATEGORIES_BY_ROLE, REOPEN_ALLOWED_STATUSES, SLA_HOURS_BY_PRIORITY
from app.core.config import settings
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.support import SupportRoutingRule, SupportTicket, SupportTicketAttachment, SupportTicketMessage
from app.models.user import User
from app.repositories.support_repository import SupportRepository
from app.schemas.common import PaginationParams
from app.services.auth.notification_service import NotificationService
from app.utils.codes import next_sequential_code
from app.utils.mailer import send_email
from app.utils.storage import get_storage_client

logger = logging.getLogger(__name__)


class SupportService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = SupportRepository(session)
        self.notifications = NotificationService(session)

    def _is_staff(self, user: User) -> bool:
        return user.role in SUPPORT_STAFF_ROLES

    def create_ticket(
        self, user: User, category: str, subject: str, description: str, priority: str,
        related_module_type: str | None, related_module_id: uuid.UUID | None,
    ) -> SupportTicket:
        allowed_categories = CATEGORIES_BY_ROLE.get(user.portal_type.value, [])
        if allowed_categories and category not in allowed_categories:
            raise BadRequestException("Invalid category for this portal")
        if priority not in SLA_HOURS_BY_PRIORITY:
            raise BadRequestException("Invalid priority")

        ticket_number = next_sequential_code(self.session, SupportTicket.ticket_number, "TCK-", width=6)
        sla_due_at = datetime.utcnow() + timedelta(hours=SLA_HOURS_BY_PRIORITY[priority])

        rule = self.repo.get_routing_rule(category)
        assigned_to_user_id = rule.default_assignee_user_id if rule else None

        ticket = self.repo.add(SupportTicket(
            ticket_number=ticket_number,
            raised_by_user_id=user.id,
            raised_by_role=user.portal_type.value,
            raised_by_org_id=user.entity_id,
            category=category,
            subject=subject,
            description=description,
            priority=priority,
            status="open",
            related_module_type=related_module_type,
            related_module_id=related_module_id,
            assigned_to_user_id=assigned_to_user_id,
            sla_due_at=sla_due_at,
        ))
        self.session.commit()

        self._send_support_email(ticket, user)
        return ticket

    def _send_support_email(self, ticket: SupportTicket, user: User) -> None:
        link = f"{settings.FRONTEND_BASE_URL}/support/tickets/{ticket.id}"
        body = (
            f"New support ticket {ticket.ticket_number}\n"
            f"Raised by: {user.name} ({user.email}) - {ticket.raised_by_role}\n"
            f"Category: {ticket.category}\nPriority: {ticket.priority}\n\n"
            f"Subject: {ticket.subject}\n\n{ticket.description}\n\nView: {link}\n"
        )
        try:
            send_email(settings.SUPPORT_EMAIL, f"[{ticket.ticket_number}] {ticket.subject}", body)
            ticket.email_sent_at = datetime.utcnow()
            self.session.commit()
        except Exception:
            logger.exception("Failed to send support ticket notification email for %s", ticket.ticket_number)

    def _get_owned_or_staff(self, user: User, ticket_id: uuid.UUID) -> SupportTicket:
        ticket = self.repo.get(ticket_id)
        if not ticket:
            raise NotFoundException("Ticket not found")
        # Org-scoped, not user-scoped -- matches list_tickets' org_id filter, so any ticket
        # visible in "My Tickets" (raised by any user in the caller's own org) is also viewable,
        # rather than only the exact ticket raised by the caller themselves.
        if not self._is_staff(user) and ticket.raised_by_org_id != user.entity_id:
            raise NotFoundException("Ticket not found")
        return ticket

    def get_detail(self, user: User, ticket_id: uuid.UUID):
        ticket = self._get_owned_or_staff(user, ticket_id)
        messages = self.repo.list_messages(ticket_id, include_internal=self._is_staff(user))
        attachments = self.repo.list_attachments(ticket_id)
        return ticket, messages, attachments

    def list_tickets(self, user: User, params: PaginationParams, **filters):
        if not self._is_staff(user):
            filters = {k: v for k, v in filters.items() if k not in ("role",)}
            return self.repo.list(params, org_id=user.entity_id, **filters)
        return self.repo.list(params, **filters)

    def add_message(self, user: User, ticket_id: uuid.UUID, message: str, is_internal_note: bool) -> SupportTicketMessage:
        ticket = self._get_owned_or_staff(user, ticket_id)
        if is_internal_note and not self._is_staff(user):
            raise ForbiddenException("Only support staff can add internal notes")

        row = self.repo.add_message(SupportTicketMessage(
            ticket_id=ticket.id, sender_user_id=user.id, sender_role=user.portal_type.value,
            message=message, is_internal_note=is_internal_note,
        ))

        if self._is_staff(user):
            if ticket.status == "open":
                ticket.status = "in_progress"
            if not is_internal_note:
                self.notifications.notify_user(
                    ticket.raised_by_user_id, "support_ticket_reply",
                    f"New reply on {ticket.ticket_number}", message[:200],
                    entity_type="support_ticket", entity_id=ticket.id,
                )
        self.session.commit()
        return row

    def update_ticket(self, user: User, ticket_id: uuid.UUID, status: str | None, priority: str | None, assigned_to_user_id: uuid.UUID | None) -> SupportTicket:
        ticket = self._get_owned_or_staff(user, ticket_id)
        is_staff = self._is_staff(user)

        if priority is not None or assigned_to_user_id is not None:
            if not is_staff:
                raise ForbiddenException("Only support staff can change priority or assignment")
            if priority is not None:
                if priority not in SLA_HOURS_BY_PRIORITY:
                    raise BadRequestException("Invalid priority")
                ticket.priority = priority
            if assigned_to_user_id is not None:
                ticket.assigned_to_user_id = assigned_to_user_id

        if status is not None:
            if status == "reopened":
                if ticket.status not in REOPEN_ALLOWED_STATUSES:
                    raise BadRequestException("Ticket can only be reopened from a resolved state")
                if not is_staff and ticket.raised_by_user_id != user.id:
                    raise ForbiddenException("Only the raiser or staff can reopen this ticket")
                window = timedelta(days=settings.SUPPORT_TICKET_REOPEN_WINDOW_DAYS)
                if ticket.resolved_at and datetime.utcnow() > ticket.resolved_at + window:
                    raise BadRequestException("Reopen window has expired")
                ticket.status = "reopened"
                ticket.resolved_at = None
                self.notifications.notify_user(
                    ticket.assigned_to_user_id or ticket.raised_by_user_id, "support_ticket_reopened",
                    f"Ticket {ticket.ticket_number} reopened", None,
                    entity_type="support_ticket", entity_id=ticket.id,
                )
            else:
                if not is_staff:
                    raise ForbiddenException("Only support staff can change ticket status")
                ticket.status = status
                if status == "resolved":
                    ticket.resolved_at = datetime.utcnow()
                    self.notifications.notify_user(
                        ticket.raised_by_user_id, "support_ticket_resolved",
                        f"Ticket {ticket.ticket_number} resolved", None,
                        entity_type="support_ticket", entity_id=ticket.id,
                    )
                elif status == "closed":
                    ticket.closed_at = datetime.utcnow()

        self.session.commit()
        return ticket

    def add_attachment(self, user: User, ticket_id: uuid.UUID, file: UploadFile, message_id: uuid.UUID | None) -> SupportTicketAttachment:
        ticket = self._get_owned_or_staff(user, ticket_id)
        uploaded = get_storage_client().save(file, folder="support-tickets")
        attachment = self.repo.add_attachment(SupportTicketAttachment(
            ticket_id=ticket.id, message_id=message_id, file_url=uploaded.url, file_name=uploaded.name,
            file_type=file.content_type or "application/octet-stream",
            file_size=file.size or 0, uploaded_by_user_id=user.id,
        ))
        self.session.commit()
        return attachment

    def list_routing_rules(self):
        return self.repo.list_routing_rules()

    def upsert_routing_rule(self, category: str, default_assignee_user_id: uuid.UUID | None, default_team: str | None):
        rule = self.repo.get_routing_rule(category)
        if rule:
            rule.default_assignee_user_id = default_assignee_user_id
            rule.default_team = default_team
        else:
            rule = self.repo.add_routing_rule(SupportRoutingRule(
                category=category, default_assignee_user_id=default_assignee_user_id, default_team=default_team,
            ))
        self.session.commit()
        return rule

    def run_sla_sweep(self) -> dict:
        """Called by scripts/support_sla_sweep.py (external cron/Task Scheduler -- no in-process
        job scheduler exists in this backend). Auto-closes resolved tickets past the reopen
        window and notifies staff of newly SLA-breached tickets."""
        closed = 0
        cutoff = datetime.utcnow() - timedelta(days=settings.SUPPORT_TICKET_REOPEN_WINDOW_DAYS)
        for ticket in self.repo.list_resolved_before(cutoff):
            ticket.status = "closed"
            ticket.closed_at = datetime.utcnow()
            closed += 1

        breached = self.repo.list_sla_breached_open()
        for ticket in breached:
            if ticket.assigned_to_user_id:
                self.notifications.notify_user(
                    ticket.assigned_to_user_id, "support_ticket_sla_breach",
                    f"SLA breached on {ticket.ticket_number}", None,
                    entity_type="support_ticket", entity_id=ticket.id,
                )
        self.session.commit()
        return {"auto_closed": closed, "sla_breached_open": len(breached)}
