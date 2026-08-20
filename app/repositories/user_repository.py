"""User (login) database access. Pure SQLAlchemy queries — no business rules here."""
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.user import PortalType, User
from app.utils.pagination import PaginationParams, paginate

_CODE_PREFIX = {
    PortalType.WAREHOUSE: "USR-WH-",
    PortalType.STORE: "USR-ST-",
    PortalType.VENDOR: "USR-VN-",
    PortalType.SUPER_ADMIN: "USR-SA-",
}


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_portal_email(self, portal_type: PortalType, email: str) -> User | None:
        stmt = select(User).where(User.portal_type == portal_type, User.email == email)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_in_entity(self, portal_type: PortalType, entity_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id, User.portal_type == portal_type, User.entity_id == entity_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_in_entity(
        self,
        portal_type: PortalType,
        entity_id: uuid.UUID,
        params: PaginationParams,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        stmt = select(User).where(User.portal_type == portal_type, User.entity_id == entity_id)
        if search:
            stmt = stmt.where(or_(User.name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
        if role:
            stmt = stmt.where(User.role == role)
        if status:
            stmt = stmt.where(User.status == status)
        if date_from:
            stmt = stmt.where(User.last_login_at >= date_from)
        if date_to:
            stmt = stmt.where(User.last_login_at <= date_to)
        stmt = stmt.order_by(User.created_at.desc())
        return paginate(self.session, stmt, params)

    def list_by_portal_type(self, portal_type: PortalType) -> list[User]:
        stmt = select(User).where(User.portal_type == portal_type)
        return list(self.session.execute(stmt).scalars().all())

    def next_code(self, portal_type: PortalType) -> str:
        """A plain row count breaks the moment any user row for this portal_type is deleted —
        it can regenerate a code that already exists and hit the User.code unique constraint.
        Basing it on the highest existing numeric suffix instead survives that."""
        prefix = _CODE_PREFIX[portal_type]
        existing = self.session.scalars(select(User.code).where(User.code.op("~")(f"^{prefix}[0-9]+$"))).all()
        next_num = max((int(c[len(prefix):]) for c in existing), default=0) + 1
        return f"{prefix}{next_num:04d}"

    def count(self) -> int:
        return self.session.execute(select(func.count()).select_from(User)).scalar_one()

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user
