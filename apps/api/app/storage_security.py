"""Safe path helpers for ClipOps storage."""

from __future__ import annotations

import re
from pathlib import Path

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_VIDEO_EXTENSIONS | {".jpg", ".jpeg", ".png", ".webp", ".txt", ".json"}


def sanitize_filename(name: str | None, *, default: str = "upload.mp4") -> str:
    raw = Path(name or default).name
    cleaned = re.sub(r"[^\w.\-]+", "_", raw).strip("._")
    if not cleaned:
        cleaned = default
    return cleaned[:180]


def assert_allowed_upload(filename: str, size: int, max_bytes: int) -> str:
    safe = sanitize_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported file type {ext or '(none)'}; allowed: {sorted(ALLOWED_VIDEO_EXTENSIONS)}")
    if size <= 0:
        raise ValueError("Empty upload")
    if size > max_bytes:
        mb = max_bytes / (1024 * 1024)
        raise ValueError(f"File exceeds max upload size ({mb:.0f} MB)")
    return safe


def resolve_under_root(root: Path, relative: str) -> Path:
    """Resolve a relative storage path; reject traversal outside root."""
    root = root.resolve()
    candidate = (root / relative).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError("Path escapes storage root")
    return candidate
