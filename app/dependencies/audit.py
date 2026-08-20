from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.audit_service import AuditService


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)
