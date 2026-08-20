import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.notification import Notification, StoreNotificationMute
from app.repositories.notification_repository import NotificationRepository
from app.utils.pagination import PaginationParams


class NotificationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = NotificationRepository(session)

    def list_for_user(self, user_id: uuid.UUID, params: PaginationParams, read: bool | None):
        items, total = self.repo.list_for_user(user_id, params, read)
        return items, total, self.repo.unread_count(user_id)

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        row = self.repo.get_for_user(user_id, notification_id)
        if not row:
            raise NotFoundException("Notification not found")
        row.read = True
        self.session.commit()
        return row

    def mark_all_read(self, user_id: uuid.UUID, notif_type: str | None = None) -> None:
        self.repo.mark_all_read(user_id, notif_type)
        self.session.commit()

    def notify_user(
        self,
        user_id: uuid.UUID,
        notif_type: str,
        title: str,
        body: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> Notification:
        """Single-recipient convenience wrapper for other domains' services (e.g. a transfer
        order notifying a store's users when their shipment dispatches) — commits immediately
        so callers don't need to know anything else about the notifications table."""
        row = self.repo.add(
            Notification(
                recipient_user_id=user_id,
                type=notif_type,
                title=title,
                body=body,
                entity_type=entity_type,
                entity_id=entity_id,
                read=False,
            )
        )
        self.session.commit()
        return row

    def create_for_roles(
        self,
        portal_type,
        entity_id: uuid.UUID,
        roles: list[str],
        title: str,
        body: str | None,
        notif_type: str,
        entity_type: str | None,
        entity_ref: uuid.UUID | None,
    ) -> list[Notification]:
        """Resolves role names to concrete recipient users at this same portal entity (e.g.
        every store-manager at this store) and creates one Notification row per match — an
        empty list is a valid response if no user currently holds any of the target roles."""
        recipients = self.repo.list_recipients(portal_type, entity_id, roles)
        created = [
            self.repo.add(
                Notification(
                    recipient_user_id=recipient.id,
                    type=notif_type,
                    title=title,
                    body=body,
                    entity_type=entity_type,
                    entity_id=entity_ref,
                    read=False,
                )
            )
            for recipient in recipients
        ]
        self.session.commit()
        return created

    def is_muted(self, store_id: uuid.UUID, role: str) -> bool:
        row = self.repo.get_mute(store_id, role)
        return bool(row and row.muted)

    def set_muted(self, store_id: uuid.UUID, role: str, muted: bool) -> None:
        row = self.repo.get_mute(store_id, role)
        if not row:
            self.repo.add_mute(StoreNotificationMute(store_id=store_id, role=role, muted=muted))
        else:
            row.muted = muted
        self.session.commit()
