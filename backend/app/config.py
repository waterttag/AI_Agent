"""Application configuration via Pydantic Settings."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve project root (parent of backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """All environment variables, loaded from .env file."""

    # Database
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'app.db'}"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ai-game-platform"
    minio_secure: bool = False

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # LLM
    llm_provider: str = "none"  # "claude" | "openai" | "deepseek" | "none"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_api_base_url: str = ""  # Custom endpoint for OpenAI-compatible APIs (optional)

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
