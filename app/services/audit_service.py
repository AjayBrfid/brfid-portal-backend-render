"""Cross-portal audit trail — written by warehouse-side actions, read by Super Admin."""
import csv
import io
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.repositories.audit_repository import AuditRepository
from app.utils.pagination import PaginationParams


class AuditService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = AuditRepository(session)

    def log(
        self,
        user_id: uuid.UUID,
        portal_type,
        action_type: str,
        description: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> AuditLog:
        row = self.repo.add(
            AuditLog(
                user_id=user_id,
                portal_type=portal_type,
                action_type=action_type,
                description=description,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )
        self.session.commit()
        return row

    def search(
        self,
        portal_type,
        params: PaginationParams,
        search_text: str | None = None,
        user_id: uuid.UUID | None = None,
        action_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        return self.repo.search(portal_type, params, search_text, user_id, action_type, date_from, date_to)

    def rows_for_report(
        self,
        portal_type: str | None,
        entity_id: uuid.UUID | None,
        date_from: date,
        date_to: date,
    ) -> list[AuditLog]:
        return self.repo.for_report(portal_type, entity_id, date_from, date_to)

    def export_csv(
        self,
        portal_type,
        search_text: str | None = None,
        user_id: uuid.UUID | None = None,
        action_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> str:
        rows = self.repo.all_matching(portal_type, search_text, user_id, action_type, date_from, date_to)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "occurred_at", "user_id", "action_type", "description", "entity_type", "entity_id"])
        for row in rows:
            writer.writerow(
                [row.id, row.occurred_at.isoformat(), row.user_id, row.action_type, row.description, row.entity_type, row.entity_id]
            )
        return buffer.getvalue()
