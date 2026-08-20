from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.auth.notification_service import NotificationService


def get_notification_service(session: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(session)
