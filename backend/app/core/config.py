# ACEA Sentinel - Production Configuration

import os
import tempfile
from pydantic_settings import BaseSettings
from typing import Optional, List
from pathlib import Path


class Settings(BaseSettings):
    PROJECT_NAME: str = "ACEA Sentinel"
    VERSION: str = "3.0.0"
    API_V1_STR: str = "/api/v1"
    
    # ========== ENVIRONMENT ==========
    # Set to "production" on Railway via env var
    ENVIRONMENT: str = "development"
    # Railway injects PORT; local default is 8000
    PORT: int = 8000
    # Frontend URL for CORS (e.g. https://your-app.vercel.app)
    FRONTEND_URL: str = ""
    
    # Gemini API
    GEMINI_API_KEYS: str = ""  # Comma separated
    
    # CodeSandbox API (deprecated - using Daytona now)
    CODESANDBOX_API_KEY: str = ""
    
    # Daytona SDK - for code execution sandboxes
    DAYTONA_API_KEY: str = ""
    
    # E2B SDK - for cloud code execution sandboxes
    E2B_API_KEY: str = ""
    E2B_TIMEOUT: int = 600  # Sandbox timeout in seconds
    
    @property
    def api_keys_list(self) -> List[str]:
        return [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"
    
    # Database — SQLite locally, PostgreSQL on Railway
    # Railway: set DATABASE_URL=postgresql://user:pass@host/db
    DATABASE_URL: str = "sqlite:///./acea.db"
    
    # Redis — localhost for dev, Upstash/Railway Redis for production
    REDIS_URL: str = "redis://localhost:6379"
    USE_REDIS_PERSISTENCE: bool = False
    
    # Security — loaded from .env; falls back to a dev-only default with warning
    JWT_SECRET: str = os.environ.get(
        "JWT_SECRET",
        "supersecretkey_change_me_in_production"  # WARN: override in .env for production
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ========== PHASE 3: PRODUCTION CONFIG ==========
    
    # File Storage — cross-platform temp directory
    PROJECTS_DIR: str = str(Path(tempfile.gettempdir()) / "acea_projects")
    MAX_PROJECT_SIZE_MB: int = 50
    
    # Rate Limiting
    MAX_REQUESTS_PER_HOUR: int = 100
    MAX_PROJECTS_PER_HOUR: int = 10
    
    # Cache
    ENABLE_CACHE: bool = True
    CACHE_TTL_HOURS: int = 24
    
    # Cleanup
    PROJECT_RETENTION_HOURS: int = 24
    ENABLE_AUTO_CLEANUP: bool = True
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "acea_studio.log"
    
    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        case_sensitive = True


settings = Settings()
