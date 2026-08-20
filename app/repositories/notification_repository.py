import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification, StoreNotificationMute
from app.models.user import PortalType, User
from app.utils.pagination import PaginationParams, paginate


class NotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_user(self, user_id: uuid.UUID, params: PaginationParams, read: bool | None):
        stmt = select(Notification).where(Notification.recipient_user_id == user_id)
        if read is not None:
            stmt = stmt.where(Notification.read == read)
        stmt = stmt.order_by(Notification.created_at.desc())
        return paginate(self.session, stmt, params)

    def unread_count(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Notification).where(
            Notification.recipient_user_id == user_id, Notification.read.is_(False)
        )
        return self.session.execute(stmt).scalar_one() or 0

    def get_for_user(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
        stmt = select(Notification).where(Notification.id == notification_id, Notification.recipient_user_id == user_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def mark_all_read(self, user_id: uuid.UUID, notif_type: str | None = None) -> None:
        q = self.session.query(Notification).filter(
            Notification.recipient_user_id == user_id, Notification.read.is_(False)
        )
        if notif_type:
            q = q.filter(Notification.type == notif_type)
        q.update({"read": True})

    def add(self, notification: Notification) -> Notification:
        self.session.add(notification)
        self.session.flush()
        return notification

    def list_recipients(self, portal_type: PortalType, entity_id: uuid.UUID, roles: list[str]) -> list[User]:
        stmt = select(User).where(User.portal_type == portal_type, User.entity_id == entity_id, User.role.in_(roles))
        return list(self.session.execute(stmt).scalars().all())

    def get_mute(self, store_id: uuid.UUID, role: str) -> StoreNotificationMute | None:
        return self.session.get(StoreNotificationMute, (store_id, role))

    def add_mute(self, row: StoreNotificationMute) -> StoreNotificationMute:
        self.session.add(row)
        self.session.flush()
        return row
