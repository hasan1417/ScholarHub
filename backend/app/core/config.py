from pydantic_settings import BaseSettings
from typing import List, Optional
import os

DEFAULT_SECRET_KEY = "your-super-secret-key-change-this-in-production"

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "ScholarHub"
    
    # Database
    DATABASE_URL: str = "postgresql://scholarhub:scholarhub@localhost:5432/scholarhub"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # Security
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 60 minutes for better UX
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # Refresh token expires in 7 days
    ACCESS_TOKEN_COOKIE_NAME: str = "access_token"
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    COOKIE_DOMAIN: Optional[str] = None
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://localhost:8080",
    ]

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/google/callback"

    # Resend Email (production)
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: str = "noreply@scholarhub.space"

    # SMTP Email (development - Mailtrap)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@scholarhub.dev"

    # Email verification & password reset token expiration
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_HOURS: int = 1

    # Frontend URL (for email links)
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Unpaywall (for OA resolution)
    UNPAYWALL_EMAIL: Optional[str] = None

    # NCBI contact email for PubMed requests
    NCBI_EMAIL: Optional[str] = None

    # Semantic Scholar API (optional, improves reliability and quotas)
    SEMANTIC_SCHOLAR_API_KEY: Optional[str] = None

    # ScienceDirect / Elsevier API (optional)
    SCIENCEDIRECT_API_KEY: Optional[str] = None

    # OpenAI (optional, for query enhancement and ranking)
    OPENAI_API_KEY: Optional[str] = None

    # OpenRouter (optional, for multi-model AI access)
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_KEY_ENCRYPTION_KEY: Optional[str] = None
    OPENROUTER_FALLBACK_MODELS_PATH: Optional[str] = None
    # Model for Rich→LaTeX conversion (optional override)
    OPENAI_CONVERSION_MODEL: Optional[str] = None
    OPENAI_PLANNER_MODEL: Optional[str] = "gpt-5.2"
    USE_OPENAI_TRANSCRIBE: bool = True
    # gpt-4o-transcribe has best accuracy for speech recognition
    OPENAI_TRANSCRIBE_MODEL: str = "gpt-4o-transcribe"

    # Development
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    
    # Chat Features
    CHAT_ASSISTANT_SLASH_ENABLED: bool = False
    
    # Alternative access (for demonstration only - disable in production)
    ENABLE_ALTERNATIVE_ACCESS: bool = False
    
    # Enhanced paper access settings
    ENABLE_UNIVERSITY_SSO_DETECTION: bool = True
    ENABLE_PDF_REDIRECT_SEARCH: bool = True
    PAPER_ACCESS_TIMEOUT: int = 30  # seconds

    # Project-first flighting
    PROJECTS_API_ENABLED: bool = False
    PROJECT_FIRST_NAV_ENABLED: bool = False
    PROJECT_REFERENCE_SUGGESTIONS_ENABLED: bool = True
    PROJECT_AI_ORCHESTRATION_ENABLED: bool = False
    PROJECT_COLLAB_REALTIME_ENABLED: bool = False
    PROJECT_MEETINGS_ENABLED: bool = False
    PROJECT_NOTIFICATIONS_ENABLED: bool = False

    # Collaboration (Phase 3)
    COLLAB_JWT_SECRET: Optional[str] = None
    COLLAB_JWT_ALGORITHM: str = "HS256"
    COLLAB_JWT_EXPIRE_SECONDS: int = 300
    COLLAB_WS_URL: str = "ws://localhost:3001"
    COLLAB_DEFAULT_ROLES: List[str] = ["editor"]
    COLLAB_BOOTSTRAP_SECRET: Optional[str] = None
    COLLAB_BOOTSTRAP_SOURCE: str = "content_json"  # content_json or content

    # Sync Space / Meetings configuration
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
    DAILY_START_CLOUD_RECORDING: bool = True
    DAILY_RECORDING_AUDIO_ONLY: bool = True
    DAILY_RAW_TRACKS_S3_BUCKET: Optional[str] = None
    DAILY_RAW_TRACKS_S3_REGION: Optional[str] = None
    DAILY_RAW_TRACKS_S3_ACCESS_KEY_ID: Optional[str] = None
    DAILY_RAW_TRACKS_S3_SECRET_ACCESS_KEY: Optional[str] = None
    DAILY_RAW_TRACKS_S3_PREFIX: Optional[str] = None
    UPLOADS_DIR: str = "uploads"
    TRANSCRIBER_BASE_URL: Optional[str] = "http://localhost:9000"
    TRANSCRIBER_ENABLED: bool = False

    # University authentication domains (comma-separated)
    UNIVERSITY_DOMAINS: str = "ieee.org,acm.org,springer.com,sciencedirect.com,wiley.com,nature.com,science.org,jstor.org"

    # Public base URL (reserved for future webhooks/integrations)
    PUBLIC_BASE_URL: Optional[str] = None

    # Deprecated: OnlyOffice integration (kept to avoid env validation errors)
    ONLYOFFICE_DOCSERVER_URL: Optional[str] = None
    ONLYOFFICE_JWT_SECRET: Optional[str] = None
    BACKEND_PUBLIC_URL: Optional[str] = None

    # Metrics / Telemetry
    ENABLE_METRICS: bool = False

    # Rate limits
    RATE_LIMIT_BACKEND: str = "100/minute"

    # LaTeX warmup
    LATEX_WARMUP_ON_STARTUP: bool = True

    # Deterministic template converter V1 (preamble in code, body via LLM)
    EDITOR_DETERMINISTIC_CONVERT_V1: bool = True

    # (Purged) Discovery advanced flags removed for simplicity
    
    class Config:
        env_file = (".env", "../.env")
        case_sensitive = True
        extra = 'ignore'

settings = Settings()

def _validate_security_settings() -> None:
    if not settings.SECRET_KEY or settings.SECRET_KEY == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY must be explicitly set and must not use the default placeholder value."
        )
    if not settings.OPENROUTER_KEY_ENCRYPTION_KEY:
        raise RuntimeError(
            "OPENROUTER_KEY_ENCRYPTION_KEY must be set to enable encryption of stored API keys."
        )

_validate_security_settings()
