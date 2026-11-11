from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    brand_name: str = "IntervueAI"
    public_web_url: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8100"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    database_url: str = "postgresql+psycopg://intervue:intervue_local_dev@localhost:54329/intervue"
    auth_secret: str = "dev-only-insecure-secret-change-me-0123456789abcdef"
    session_ttl_hours: int = 72
    cookie_secure: bool = False

    google_client_id: str = ""
    google_client_secret: str = ""

    ai_provider: Literal["mock", "anthropic", "openai", "gemini", "openai_compat"] = "mock"
    ai_api_key: str = ""
    ai_base_url: str = ""  # openai_compat (Groq, OpenRouter, Ollama); optional override for gemini
    ai_model: str = "claude-opus-5-5"
    ai_fallback_model: str = ""
    ai_fast_model: str = ""  # latency-sensitive turns (follow-ups, personalisation, code review); defaults to ai_model
    ai_timeout_seconds: float = 60.0

    voice_provider: Literal["browser", "edge", "elevenlabs", "mock"] = "browser"
    voice_api_key: str = ""
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    embedding_provider: Literal["local"] = "local"
    screen_analysis_provider: Literal["mock", "ai"] = "mock"

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = str(REPO_ROOT / "var" / "storage")
    storage_s3_bucket: str = ""
    storage_s3_region: str = "ap-south-1"
    storage_url: str = ""

    worker_url: str = "http://localhost:8101"
    worker_token: str = "change-me-worker-token"

    pricing_config_path: str = ""
    usd_inr_rate: float = 83.0
    data_retention_days: int = 365

    max_upload_mb: int = 8
    demo_enabled: bool = True
    demo_duration_minutes: int = 8
    max_followups: int = 2

    @model_validator(mode="after")
    def _finalize(self) -> Settings:
        if not self.pricing_config_path:
            self.pricing_config_path = str(REPO_ROOT / "config" / "pricing.json")
        if self.environment == "production":
            if self.auth_secret.startswith("dev-only") or len(self.auth_secret) < 32:
                raise ValueError("AUTH_SECRET must be set to a strong random value in production")
            if self.worker_token == "change-me-worker-token":
                raise ValueError("WORKER_TOKEN must be set in production")
            self.cookie_secure = True
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
