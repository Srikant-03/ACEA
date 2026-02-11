# ACEA Sentinel - Production Configuration

from pydantic_settings import BaseSettings
from typing import Optional, List
from pathlib import Path


class Settings(BaseSettings):
    PROJECT_NAME: str = "ACEA Sentinel"
    VERSION: str = "3.0.0"
    API_V1_STR: str = "/api/v1"
    
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
    
    # Database
    DATABASE_URL: str = "sqlite:///./acea.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    USE_REDIS_PERSISTENCE: bool = False
    
    # Security
    JWT_SECRET: str = "supersecretkey_change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ========== PHASE 3: PRODUCTION CONFIG ==========
    
    # File Storage
    PROJECTS_DIR: str = "/tmp/acea_projects"
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
