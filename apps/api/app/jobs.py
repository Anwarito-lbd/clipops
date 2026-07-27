"""Enqueue Celery tasks or run inline for reliable local Operator Mode."""

from __future__ import annotations

from typing import Any, Callable

from app.config import get_settings


def enqueue_or_run(task: Any, *args: Any, **kwargs: Any) -> Any:
    """
    Run Celery task async when broker+eager=false; otherwise call synchronously.

    Prevents assets stuck at IMPORTED when Redis is up but no worker is running
    (local default: CELERY_EAGER=true).
    """
    settings = get_settings()
    if getattr(settings, "celery_eager", True):
        return task(*args, **kwargs)
    try:
        return task.delay(*args, **kwargs)
    except Exception:
        return task(*args, **kwargs)


def media_preview_url(storage_root: str, video_path: str | None, root: Any = None) -> str | None:
    from pathlib import Path

    if not video_path:
        return None
    sr = Path(storage_root)
    if not sr.is_absolute() and root is not None:
        sr = Path(root) / sr
    vp = Path(video_path)
    try:
        if vp.is_absolute():
            rel = vp.resolve().relative_to(sr.resolve())
            return f"/api/media/{rel.as_posix()}"
        return f"/api/media/{str(video_path).replace(chr(92), '/')}"
    except Exception:
        return f"/api/media/{str(video_path).replace(chr(92), '/')}"
