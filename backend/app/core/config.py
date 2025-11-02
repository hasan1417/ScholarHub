from pydantic_settings import BaseSettings
from typing import List, Optional
import os

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "ScholarHub"
    
    # Database
    DATABASE_URL: str = "postgresql://scholarhub:scholarhub@localhost:5432/scholarhub"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # Security
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours for testing
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # Refresh token expires in 7 days
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://localhost:8080",
    ]
    
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
    # Model for Rich→LaTeX conversion (optional override)
    OPENAI_CONVERSION_MODEL: Optional[str] = None
    OPENAI_PLANNER_MODEL: Optional[str] = "gpt-5"
    USE_OPENAI_TRANSCRIBE: bool = True
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

    # LaTeX warmup
    LATEX_WARMUP_ON_STARTUP: bool = True

    # (Purged) Discovery advanced flags removed for simplicity
    
    class Config:
        env_file = (".env", "../.env")
        case_sensitive = True
        extra = 'ignore'

settings = Settings()
