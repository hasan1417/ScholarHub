from functools import lru_cache
from typing import List, Optional
import os

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings


DEV_SECRET = "dev-secret-key"
DEV_DATABASE_URL = "postgresql://scholarhub:scholarhub@localhost:5432/scholarhub"
DEV_REDIS_URL = "redis://localhost:6379"


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = Field(default="development", alias="ENVIRONMENT")
    DEBUG: bool = Field(default=True, alias="DEBUG")

    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "ScholarHub"

    # Database / cache
    DATABASE_URL: str = Field(default=DEV_DATABASE_URL, alias="DATABASE_URL")
    REDIS_URL: str = Field(default=DEV_REDIS_URL, alias="REDIS_URL")

    # Security
    SECRET_KEY: str = Field(default=DEV_SECRET, alias="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ACCESS_TOKEN_COOKIE_NAME: str = Field(default="scholarhub_at", alias="ACCESS_TOKEN_COOKIE_NAME")
    REFRESH_TOKEN_COOKIE_NAME: str = Field(default="scholarhub_rt", alias="REFRESH_TOKEN_COOKIE_NAME")
    COOKIE_DOMAIN: Optional[str] = Field(default=None, alias="COOKIE_DOMAIN")

    # Rate limiting
    RATE_LIMIT_BACKEND: str = Field(default="5/minute", alias="RATE_LIMIT_BACKEND")
    RATE_LIMIT_REGISTER: str = Field(default="2/minute", alias="RATE_LIMIT_REGISTER")

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:5500",
            "http://localhost:5500",
            "http://localhost:8080",
        ]
    )

    # Optional external integrations
    UNPAYWALL_EMAIL: Optional[str] = None
    NCBI_EMAIL: Optional[str] = None
    SEMANTIC_SCHOLAR_API_KEY: Optional[str] = None
    SCIENCEDIRECT_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_CONVERSION_MODEL: Optional[str] = None
    OPENAI_PLANNER_MODEL: Optional[str] = "gpt-5"
    USE_OPENAI_TRANSCRIBE: bool = True
    OPENAI_TRANSCRIBE_MODEL: str = "gpt-4o-transcribe"

    # Feature flags
    CHAT_ASSISTANT_SLASH_ENABLED: bool = False
    ENABLE_ALTERNATIVE_ACCESS: bool = False
    ENABLE_UNIVERSITY_SSO_DETECTION: bool = True
    ENABLE_PDF_REDIRECT_SEARCH: bool = True
    PAPER_ACCESS_TIMEOUT: int = 30

    PROJECTS_API_ENABLED: bool = False
    PROJECT_FIRST_NAV_ENABLED: bool = False
    PROJECT_REFERENCE_SUGGESTIONS_ENABLED: bool = True
    PROJECT_AI_ORCHESTRATION_ENABLED: bool = False
    PROJECT_COLLAB_REALTIME_ENABLED: bool = False
    PROJECT_MEETINGS_ENABLED: bool = False
    PROJECT_NOTIFICATIONS_ENABLED: bool = False

    COLLAB_JWT_SECRET: Optional[str] = None
    COLLAB_JWT_ALGORITHM: str = "HS256"
    COLLAB_JWT_EXPIRE_SECONDS: int = 300
    COLLAB_WS_URL: str = "ws://localhost:3001"
    COLLAB_DEFAULT_ROLES: List[str] = Field(default_factory=lambda: ["editor"])

    SYNC_ROOM_PREFIX: str = "sync"
    DAILY_API_BASE_URL: str = "https://api.daily.co/v1"
    DAILY_API_KEY: Optional[str] = None
    DAILY_DOMAIN: Optional[str] = None
    DAILY_ROOM_BASE_URL: Optional[str] = None
    DAILY_ROOM_TTL_SECONDS: int = 6 * 3600
    DAILY_TOKEN_TTL_SECONDS: int = 3600
    SYNC_CALLBACK_TOKEN: Optional[str] = None
    DAILY_WEBHOOK_SECRET: Optional[str] = None
    DAILY_WEBHOOK_URL: Optional[str] = None
    DAILY_ENABLE_RECORDING: Optional[str] = "cloud"
    DAILY_START_CLOUD_RECORDING: bool = False
    DAILY_RECORDING_AUDIO_ONLY: bool = False
    DAILY_RAW_TRACKS_S3_BUCKET: Optional[str] = None
    DAILY_RAW_TRACKS_S3_REGION: Optional[str] = None
    DAILY_RAW_TRACKS_S3_ACCESS_KEY_ID: Optional[str] = None
    DAILY_RAW_TRACKS_S3_SECRET_ACCESS_KEY: Optional[str] = None
    DAILY_RAW_TRACKS_S3_PREFIX: Optional[str] = None
    UPLOADS_DIR: str = "uploads"
    TRANSCRIBER_BASE_URL: Optional[str] = "http://localhost:9000"
    TRANSCRIBER_ENABLED: bool = False

    UNIVERSITY_DOMAINS: str = (
        "ieee.org,acm.org,springer.com,sciencedirect.com,wiley.com,nature.com,science.org,jstor.org"
    )
    PUBLIC_BASE_URL: Optional[str] = None

    ONLYOFFICE_DOCSERVER_URL: Optional[str] = None
    ONLYOFFICE_JWT_SECRET: Optional[str] = None
    BACKEND_PUBLIC_URL: Optional[str] = None

    ENABLE_METRICS: bool = False
    LATEX_WARMUP_ON_STARTUP: bool = True

    class Config:
        env_file = (".env", "../.env")
        case_sensitive = True
        extra = "ignore"

    @model_validator(mode="after")
    def validate_security_critical(self):
        is_dev = (self.ENVIRONMENT or "development").lower() == "development"
        missing = []

        if not self.SECRET_KEY or self.SECRET_KEY == DEV_SECRET:
            if not is_dev:
                missing.append("SECRET_KEY")

        if not self.DATABASE_URL or self.DATABASE_URL == DEV_DATABASE_URL:
            if not is_dev:
                missing.append("DATABASE_URL")

        if not self.REDIS_URL or self.REDIS_URL == DEV_REDIS_URL:
            if not is_dev:
                missing.append("REDIS_URL")

        if missing:
            raise ValidationError(
                [
                    {
                        "loc": ("configuration",),
                        "msg": f"Missing required environment settings: {', '.join(missing)}",
                        "type": "value_error.missing",
                    }
                ],
                Settings,
            )

        if not is_dev and self.DEBUG:
            raise ValidationError(
                [
                    {
                        "loc": ("DEBUG",),
                        "msg": "DEBUG must be False outside development",
                        "type": "value_error",
                    }
                ],
                Settings,
            )

        # Restrict default CORS origins in production if user hasn't overridden them
        if not is_dev:
            localhost_origins = {origin for origin in self.BACKEND_CORS_ORIGINS if "localhost" in origin or "127.0.0.1" in origin}
            if localhost_origins and len(set(self.BACKEND_CORS_ORIGINS)) == len(localhost_origins):
                raise ValidationError(
                    [
                        {
                            "loc": ("BACKEND_CORS_ORIGINS",),
                            "msg": "BACKEND_CORS_ORIGINS must be set to explicit production origins",
                            "type": "value_error",
                        }
                    ],
                    Settings,
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
