"""Read what a rendered file actually contains.

Compliance previously took aspect ratio, duration and audio presence as
arguments supplied by the caller, so it asserted things nobody had checked. A
clip could report "9:16, passed" while being 16:9 with no audio track.

ffprobe answers three of those questions definitively. Logo and on-screen CTA
detection would need vision and stay unverified - but a check that knows what it
cannot see is worth more than one that assumes.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from math import gcd
from typing import Any


@dataclass
class MediaFacts:
    ok: bool
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    duration_sec: float | None = None
    has_audio: bool | None = None
    audio_silent: bool | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio_label(width: int, height: int) -> str:
    if not width or not height:
        return "unknown"
    d = gcd(width, height)
    return f"{width // d}:{height // d}"


def probe(path: str, ffprobe: str = "ffprobe", timeout: float = 30.0) -> MediaFacts:
    """Inspect a rendered clip. Never raises - a failed probe reports itself."""
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v", "error",
                "-print_format", "json",
                "-show_streams",
                "-show_format",
                path,
            ],
            text=True,
            timeout=timeout,
        )
        data = json.loads(out)
    except Exception as exc:  # noqa: BLE001
        return MediaFacts(ok=False, error=str(exc)[:200])

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    if video is None:
        return MediaFacts(ok=False, has_audio=audio is not None, error="No video stream")

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)

    duration = None
    for source in (data.get("format", {}).get("duration"), video.get("duration")):
        try:
            duration = float(source)
            break
        except (TypeError, ValueError):
            continue

    return MediaFacts(
        ok=True,
        width=width or None,
        height=height or None,
        aspect_ratio=_ratio_label(width, height),
        duration_sec=round(duration, 2) if duration else None,
        has_audio=audio is not None,
    )


def audio_is_silent(
    path: str, ffmpeg: str = "ffmpeg", threshold_db: float = -60.0, timeout: float = 60.0
) -> bool | None:
    """True when the audio track is effectively silent.

    A clip trimmed slightly off can carry an audio stream containing nothing,
    which passes a "has audio" check while being unwatchable. Returns None when
    the measurement could not be taken rather than guessing.
    """
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", path,
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001
        return None

    for line in (proc.stderr or "").splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].split("dB")[0].strip()) < threshold_db
            except (IndexError, ValueError):
                return None
    return None
