from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.auth.user_management_service import UserManagementService


def get_user_management_service(session: Session = Depends(get_db)) -> UserManagementService:
    return UserManagementService(session)
