from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "ACEA Sentinel"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Gemini API
    # Gemini API
    GEMINI_API_KEYS: str = "" # Comma separated
    
    @property
    def api_keys_list(self):
        return [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]
    
    # Database
    DATABASE_URL: str = "sqlite:///./acea.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # Security
    JWT_SECRET: str = "supersecretkey_change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        # Calculate absolute path to .env file (backend/.env)
        # __file__ is backend/app/core/config.py
        # parent -> core, parent -> app, parent -> backend
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        case_sensitive = True

settings = Settings()
