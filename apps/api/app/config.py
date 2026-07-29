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

    # Commentary-account TTS (Edge TTS) mixed onto campaign footage — off by default
    enable_tts_commentary: bool = False
    tts_voice: str = "en-US-JennyNeural"

    tiktok_url: str = "https://www.tiktok.com"
    youtube_url: str = "https://studio.youtube.com"
    twitter_url: str = "https://x.com"
    content_rewards_url: str = "https://www.contentrewards.com"
    # Amazon Associates tag for affiliate URL builder (operator pastes product URLs)
    amazon_affiliate_tag: str = ""
    # Public CR discover board (Scrapling Fetcher — no login, no auto-join)
    scrapling_discover_url: str = "https://whop.com/discover/content-rewards/"
    scrapling_enabled: bool = True
    # Official OAuth posting (optional — requires developer apps + audit)
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = "http://127.0.0.1:8000/api/oauth/tiktok/callback"
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://127.0.0.1:8000/api/oauth/youtube/callback"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
