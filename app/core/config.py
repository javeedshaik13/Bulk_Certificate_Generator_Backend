import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Bulk Certificate Generator API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str = "sqlite:///./certificates.db"

    # File Storage
    STORAGE_BACKEND: str = "local"
    STORAGE_BASE_DIR: str = str(BASE_DIR / "storage" / "certificates")
    MAX_CONCURRENT_WORKERS: int = 4
    MAX_RECIPIENTS_PER_JOB: int = 1000

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])


settings = Settings()

# Ensure storage directory exists
os.makedirs(settings.STORAGE_BASE_DIR, exist_ok=True)
