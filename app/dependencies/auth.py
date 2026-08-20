"""Authentication/authorization dependencies for protected routes, shared by all four portals.
Decodes the bearer JWT and loads the User — the authenticated identity, never a client-supplied
id, is the source of truth for "who is making this request."
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, InvalidTokenException, UserNotFoundException
from app.core.security import decode_access_token
from app.dependencies.database import get_db
from app.models.user import User, UserStatus
from app.services.auth.auth_service import AuthService

_bearer_scheme = HTTPBearer(auto_error=True)


def get_auth_service(session: Session = Depends(get_db)) -> AuthService:
    return AuthService(session)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise InvalidTokenException(str(exc)) from exc
    user = db.get(User, payload["sub"])
    if not user or user.status != UserStatus.ACTIVE:
        raise UserNotFoundException()
    return user


def require_portal(portal_type: str):
    """Every router mounted under a given URL prefix (e.g. /api/v1/warehouse/...) must also
    enforce that the caller's JWT actually belongs to that portal — otherwise a valid
    store-portal token could be replayed against a warehouse URL just by guessing it."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.portal_type.value != portal_type:
            raise ForbiddenException(f"This endpoint belongs to the {portal_type} portal")
        return user

    return _dep


def require_role(*allowed_roles: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise ForbiddenException("You do not have permission to perform this action")
        return user

    return _dep
