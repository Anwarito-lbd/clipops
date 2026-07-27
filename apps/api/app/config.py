from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[3]
_ENV_CANDIDATES = (
    str(_ROOT / ".env"),
    str(Path.cwd() / ".env"),
    ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_CANDIDATES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    operator_email: str = "operator@clipops.local"
    # Dev default only — set OPERATOR_PASSWORD_HASH (bcrypt) for real use
    operator_password: str = "changeme"
    operator_password_hash: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    # development | production — production refuses weak secrets at startup
    clipops_env: str = "development"

    database_url: str = "sqlite:///./clipops.db"
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    storage_bucket: str = "clipops"

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/1"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    whisperx_model: str = "medium"
    whisperx_device: str = "cuda"
    whisperx_compute_type: str = "float16"
    hf_token: str = ""
    enable_diarization: bool = True

    platform_fee_multiplier: float = 0.93
    budget_utilisation_reject_threshold: float = 0.90
    view_validation_days: int = 3
    submission_review_days: int = 7

    storage_root: str = str(_ROOT / "storage")
    ffmpeg_path: str = "ffmpeg"
    auto_editor_enabled: bool = False
    remotion_url: str = "http://127.0.0.1:3100"
    burn_captions: bool = True
    max_upload_mb: int = 512
    # Local default: run pipeline inline so uploads don't hang without a worker
    celery_eager: bool = True

    tiktok_url: str = "https://www.tiktok.com"
    content_rewards_url: str = "https://www.contentrewards.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
