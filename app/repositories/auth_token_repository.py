"""Refresh/password-reset token and per-user preference-panel database access."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import PasswordResetToken, RefreshToken, UserAccountSettings, UserNotificationPrefs


class AuthTokenRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_refresh_token(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.session.execute(stmt).scalar_one_or_none()

    def add_reset_token(self, token: PasswordResetToken) -> PasswordResetToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_reset_token_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_account_settings(self, user_id: uuid.UUID) -> UserAccountSettings | None:
        return self.session.get(UserAccountSettings, user_id)

    def add_account_settings(self, row: UserAccountSettings) -> UserAccountSettings:
        self.session.add(row)
        self.session.flush()
        return row

    def get_notification_prefs(self, user_id: uuid.UUID) -> UserNotificationPrefs | None:
        return self.session.get(UserNotificationPrefs, user_id)

    def add_notification_prefs(self, row: UserNotificationPrefs) -> UserNotificationPrefs:
        self.session.add(row)
        self.session.flush()
        return row
