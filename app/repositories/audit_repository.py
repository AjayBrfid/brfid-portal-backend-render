import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User
from app.utils.pagination import PaginationParams, paginate


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, row: AuditLog) -> AuditLog:
        self.session.add(row)
        self.session.flush()
        return row

    def _search_stmt(
        self,
        portal_type,
        search: str | None,
        user_id: uuid.UUID | None,
        action_type: str | None,
        date_from: date | None,
        date_to: date | None,
    ):
        stmt = select(AuditLog).where(AuditLog.portal_type == portal_type)
        if search:
            stmt = stmt.where(AuditLog.description.ilike(f"%{search}%"))
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if action_type:
            stmt = stmt.where(AuditLog.action_type == action_type)
        if date_from:
            stmt = stmt.where(AuditLog.occurred_at >= date_from)
        if date_to:
            stmt = stmt.where(AuditLog.occurred_at <= date_to)
        return stmt.order_by(AuditLog.occurred_at.desc())

    def search(
        self,
        portal_type,
        params: PaginationParams,
        search_text: str | None,
        user_id: uuid.UUID | None,
        action_type: str | None,
        date_from: date | None,
        date_to: date | None,
    ):
        stmt = self._search_stmt(portal_type, search_text, user_id, action_type, date_from, date_to)
        return paginate(self.session, stmt, params)

    def all_matching(
        self,
        portal_type,
        search_text: str | None,
        user_id: uuid.UUID | None,
        action_type: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[AuditLog]:
        stmt = self._search_stmt(portal_type, search_text, user_id, action_type, date_from, date_to)
        return list(self.session.scalars(stmt).all())

    def for_report(
        self,
        portal_type: str | None,
        entity_id: uuid.UUID | None,
        date_from: date,
        date_to: date,
    ) -> list[AuditLog]:
        """Used only by the Activity Report .xlsx export -- deliberately separate from
        _search_stmt so the existing warehouse Audit Log page's behavior (portal-only filter,
        inclusive date_to) is untouched. portal_type=None means "all portals" (Super Admin);
        entity_id scopes to one vendor/warehouse/store's own users, since AuditLog itself has
        no vendor_id/warehouse_id/store_id column -- without this, a portal-only filter would
        leak every other tenant's activity into a report branded with one entity's details."""
        start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        stmt = select(AuditLog).where(AuditLog.occurred_at >= start, AuditLog.occurred_at < end)
        if portal_type is not None:
            stmt = stmt.where(AuditLog.portal_type == portal_type)
        if entity_id is not None:
            user_ids = select(User.id).where(User.entity_id == entity_id)
            if portal_type is not None:
                user_ids = user_ids.where(User.portal_type == portal_type)
            stmt = stmt.where(AuditLog.user_id.in_(user_ids))
        results = list(self.session.scalars(stmt.order_by(AuditLog.occurred_at.desc())).all())

        # AuditLog carries no ORM relationship to User (this codebase resolves entity/user
        # links manually everywhere, never via relationship() -- see models/user.py's own
        # docstring on this) -- so batch-fetch names for the report's "Performed By" column
        # in one extra query instead of N+1ing per row, and stash it as a plain attribute
        # (transient, not persisted) for excel_export.py to read.
        names = {}
        if results:
            names = dict(self.session.execute(select(User.id, User.name).where(User.id.in_({r.user_id for r in results}))).all())
        for r in results:
            r.performed_by_name = names.get(r.user_id, "-")
        return results
