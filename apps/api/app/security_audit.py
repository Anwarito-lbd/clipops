"""Startup / health checks for secrets and media stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def media_stack_status() -> dict[str, Any]:
    out: dict[str, Any] = {
        "torch": False,
        "cuda": False,
        "device_name": None,
        "whisperx": False,
        "faster_whisper": False,
        "scenedetect": False,
    }
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
    return out
