"""Snap ranked segment boundaries to complete sentences.

Thin adapter over vendor/claude-shorts/snap_boundaries.py, which was vendored
but never called. Without it clips end wherever the ranker's segment happened to
stop - mid-sentence, mid-word - and the clip reads as unfinished no matter how
good the selection was. One measured example ended on "...is just one outcome
on", three seconds short of the sentence.

The vendored file is a CLI script with no package, so it is loaded by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "claude-shorts" / "snap_boundaries.py"


def _load_vendor():
    if not _VENDOR.is_file():
        return None
    key = "clipops_vendor_snap_boundaries"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _VENDOR)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def snap_segments(
    segments: list[dict[str, Any]],
    transcript: dict[str, Any],
    *,
    max_sec: float = 25.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (segments, adjustments) with start/end snapped to sentence bounds.

    Segments are returned unchanged when the transcript carries no word-level
    timestamps - a heuristic transcript has none, and snapping against absent
    data would move boundaries to arbitrary places.
    """
    vendor = _load_vendor()
    if vendor is None:
        return segments, []

    words: list[dict[str, Any]] = []
    for seg in transcript.get("segments") or []:
        for w in seg.get("words") or []:
            if w.get("start") is None or w.get("end") is None:
                continue
            words.append(
                {"text": str(w.get("word", "")).strip(), "start": w["start"], "end": w["end"]}
            )
    words.sort(key=lambda w: w["start"])
    if not words:
        return segments, []

    out: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    for seg in segments:
        old_start = float(seg["start_sec"])
        old_end = float(seg["end_sec"])
        new_start = float(vendor.snap_start(words, old_start))
        new_end = float(vendor.snap_end(words, old_end))

        # Completing a sentence must not push the clip past the band ceiling,
        # which would fail the campaign's duration rule.
        if new_end - new_start > max_sec:
            new_end = new_start + max_sec
        if new_end <= new_start:
            new_start, new_end = old_start, old_end

        updated = dict(seg)
        updated["start_sec"] = round(new_start, 3)
        updated["end_sec"] = round(new_end, 3)
        out.append(updated)
        if (round(new_start, 2), round(new_end, 2)) != (round(old_start, 2), round(old_end, 2)):
            adjustments.append(
                {
                    "old": f"{old_start:.2f}-{old_end:.2f}",
                    "new": f"{new_start:.2f}-{new_end:.2f}",
                    "delta_end_ms": round((new_end - old_end) * 1000),
                }
            )
    return out, adjustments
