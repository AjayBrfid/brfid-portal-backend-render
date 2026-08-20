"""Password hashing, JWT access tokens, and opaque refresh/reset tokens.

Two decisions carried over from the source-project comparison (see the consolidation plan):
- bcrypt is called directly, never through passlib.CryptContext — passlib 1.7.4 (its last
  release) does a version-detection self-test against the installed bcrypt backend that raises
  on bcrypt>=4.1's stricter 72-byte-password check, crashing on every hash/verify call.
- Refresh tokens and password-reset tokens are opaque random strings, not JWTs — only their
  SHA-256 hash is ever persisted (RefreshToken.token_hash / PasswordResetToken.token_hash), so a
  leaked DB row alone can't be replayed as a valid token. Access tokens are short-lived JWTs.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt as pyjwt

from app.core.config import settings

_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode()[:_BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode()[:_BCRYPT_MAX_BYTES], hashed.encode())


def create_access_token(user_id: uuid.UUID, portal_type: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "portal_type": portal_type, "role": role, "exp": expire, "type": "access"}
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = pyjwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except pyjwt.PyJWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("type") != "access":
        raise ValueError("Not an access token")
    return payload


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
