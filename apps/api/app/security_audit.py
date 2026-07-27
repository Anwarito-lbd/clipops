"""Startup / health checks for secrets and media stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.request import urlopen


WEAK_JWT = {
    "",
    "dev-secret-change-me",
    "replace-with-long-random-string",
    "changeme",
    "secret",
}


@dataclass
class SecurityReport:
    ok: bool
    env: str
    using_password_hash: bool
    jwt_ok: bool
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "env": self.env,
            "using_password_hash": self.using_password_hash,
            "jwt_ok": self.jwt_ok,
            "messages": self.messages,
        }


def audit_settings(settings: Any) -> SecurityReport:
    env = (getattr(settings, "clipops_env", None) or "development").lower()
    messages: list[str] = []
    jwt = getattr(settings, "jwt_secret", "") or ""
    jwt_ok = jwt not in WEAK_JWT and len(jwt) >= 32
    using_hash = bool(getattr(settings, "operator_password_hash", "") or "")
    plain = getattr(settings, "operator_password", "") or ""

    if not jwt_ok:
        messages.append("JWT_SECRET is weak or default — run scripts/rotate_secrets.py")
    if env == "production":
        if not using_hash:
            messages.append("production requires OPERATOR_PASSWORD_HASH")
        if plain in {"changeme", "password", "admin"}:
            messages.append("production must not use weak OPERATOR_PASSWORD")
        if not jwt_ok:
            messages.append("production refuses weak JWT_SECRET")
    elif not using_hash and plain == "changeme":
        messages.append("demo password in use — rotate before any shared deploy")

    ok = True
    if env == "production":
        ok = jwt_ok and using_hash and plain not in {"changeme", "password", "admin"}

    return SecurityReport(
        ok=ok,
        env=env,
        using_password_hash=using_hash,
        jwt_ok=jwt_ok,
        messages=messages,
    )


def _ping_redis(url: str) -> bool:
    try:
        import redis  # type: ignore

        client = redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
        return client.ping() is True
    except Exception:
        return False


def _ping_remotion(url: str) -> bool:
    try:
        with urlopen(url.rstrip("/") + "/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def media_stack_status(settings: Any | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "torch": False,
        "cuda": False,
        "device_name": None,
        "whisperx": False,
        "faster_whisper": False,
        "scenedetect": False,
        "ffmpeg": False,
        "redis": False,
        "remotion": False,
        "celery_eager": True,
        "hf_token_set": False,
        "diarization_ready": False,
    }
    try:
        import shutil

        out["ffmpeg"] = bool(shutil.which("ffmpeg"))
    except Exception:
        pass
    try:
        import torch

        out["torch"] = True
        out["cuda"] = bool(torch.cuda.is_available())
        if out["cuda"]:
            out["device_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        out["torch_error"] = str(exc)
    try:
        import whisperx  # noqa: F401

        out["whisperx"] = True
    except Exception:
        pass
    try:
        import faster_whisper  # noqa: F401

        out["faster_whisper"] = True
    except Exception:
        pass
    try:
        import scenedetect  # noqa: F401

        out["scenedetect"] = True
    except Exception:
        pass

    if settings is not None:
        out["celery_eager"] = bool(getattr(settings, "celery_eager", True))
        out["hf_token_set"] = bool(getattr(settings, "hf_token", "") or "")
        out["diarization_ready"] = bool(
            out["whisperx"] and out["hf_token_set"] and getattr(settings, "enable_diarization", True)
        )
        out["redis"] = _ping_redis(getattr(settings, "redis_url", "redis://127.0.0.1:6379/0"))
        out["remotion"] = _ping_remotion(getattr(settings, "remotion_url", "http://127.0.0.1:3100"))
    else:
        out["redis"] = _ping_redis("redis://127.0.0.1:6379/0")
        out["remotion"] = _ping_remotion("http://127.0.0.1:3100")

    # Readiness score 0–100 for operator dashboard
    checks = [
        out["ffmpeg"],
        out["torch"] and out["cuda"],
        out["whisperx"] or out["faster_whisper"],
        out["scenedetect"],
        out["remotion"],
        out["redis"] or out["celery_eager"],
    ]
    out["readiness_pct"] = round(100 * sum(1 for c in checks if c) / len(checks))
    out["mode"] = "eager_inline" if out["celery_eager"] else "async_celery"
    return out
