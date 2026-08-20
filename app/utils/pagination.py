from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import PaginationParams


def paginate(db: Session, stmt, params: PaginationParams):
    """Runs a COUNT of the given select statement, then applies offset/limit and returns
    (items, total_items). Callers pass a SQLAlchemy 2.0 `select(...)` statement, not raw rows.
    Shared by every repository's list_* method across all four portals."""
    total_items = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.offset(params.offset).limit(params.limit)).all()
    return items, total_items
