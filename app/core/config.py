"""Application settings loaded from environment variables / .env file.

Field naming/shape follows the brfid-portal-backend convention (DATABASE_HOST/PORT/NAME/USER/
PASSWORD, computed sqlalchemy_database_url) since 2 of the 3 source projects already used it;
the JWT/refresh/files/rate-limit fields are carried over from Backend-WH-Retail, the only one of
the three that had a fuller auth + file-storage story.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "brfid_platform"
    DATABASE_USER: str = "brfid_user"
    DATABASE_PASSWORD: str = "brfid_password"
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    TEST_DATABASE_URL: str | None = None

    JWT_SECRET_KEY: str = "change-me-to-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_TTL_HOURS: int = 1

    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    # SeaweedFS Filer HTTP API (also exposes an S3-compatible gateway) — see app/utils/storage.py.
    FILES_STORAGE_BACKEND: str = "seaweedfs"
    SEAWEEDFS_FILER_URL: str = "http://localhost:8888"
    FILES_LOCAL_DIR: str = "./uploads"
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_ENDPOINT_URL: str = ""

    RATE_LIMIT_PER_MINUTE: int = 120

    # Support ticketing (app/utils/mailer.py + app/services/support/support_service.py).
    # No email-sending service existed anywhere in this backend before this feature -- these
    # SMTP_* fields back a small stdlib smtplib mailer rather than pulling in a new dependency.
    SUPPORT_EMAIL: str = "support@britanniarfids.com"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_FROM_ADDRESS: str = "no-reply@britanniarfids.com"
    SUPPORT_TICKET_REOPEN_WINDOW_DAYS: int = 3

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
