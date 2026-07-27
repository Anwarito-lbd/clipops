"""Score transcript+scene segments for viral clip potential."""

from __future__ import annotations

import re
from typing import Any

HOOK_WORDS = re.compile(
    r"\b(wait|secret|nobody|surprising|shocking|mistake|truth|never|always|why|how)\b",
    re.I,
)
CONFLICT = re.compile(r"\b(but|however|instead|wrong|fail|problem|vs|versus)\b", re.I)
EMOTION = re.compile(r"\b(love|hate|cry|crazy|insane|amazing|fear|angry|wow)\b", re.I)
PAYOFF = re.compile(r"\b(so|therefore|result|finally|that'?s why|payoff|answer)\b", re.I)


def _score_text(text: str, campaign_name: str) -> dict[str, float]:
    t = text or ""
    opening = t.strip().split(".")[0] if t.strip() else ""
    scores = {
        "strong_opening": 90.0 if HOOK_WORDS.search(opening) else (60.0 if opening else 20.0),
        "curiosity": 85.0 if HOOK_WORDS.search(t) else 40.0,
        "conflict_surprise": 80.0 if CONFLICT.search(t) else 35.0,
        "emotional_reaction": 75.0 if EMOTION.search(t) else 30.0,
        "clear_payoff": 80.0 if PAYOFF.search(t) else 40.0,
        "standalone_clarity": 70.0 if 8 <= len(t.split()) <= 80 else 45.0,
        "campaign_relevance": 80.0
        if campaign_name and campaign_name.lower().split()[0] in t.lower()
        else 55.0,
    }
    return scores


def rank_segments(transcript: dict[str, Any], scenes: dict[str, Any], campaign_name: str) -> list[dict]:
    segments = transcript.get("segments") or []
    scene_list = scenes.get("scenes") or []
    candidates: list[dict] = []

    # Prefer scene windows; overlay transcript text overlapping the window
    windows = scene_list or [{"start_sec": s.get("start", 0), "end_sec": s.get("end", 10)} for s in segments]

    for win in windows:
        start = float(win.get("start_sec", win.get("start", 0)))
        end = float(win.get("end_sec", win.get("end", start + 10)))
        if end - start < 3:
            continue
        # Cap window to ~60s for ranking
        if end - start > 60:
            end = start + 60
        texts = []
        for seg in segments:
            s0 = float(seg.get("start", 0))
            s1 = float(seg.get("end", 0))
            if s1 >= start and s0 <= end:
                texts.append(seg.get("text", "").strip())
        text = " ".join(texts).strip() or "Hook moment from source footage."
        scores = _score_text(text, campaign_name)
        total = sum(scores.values()) / len(scores)
        candidates.append(
            {
                "start_sec": start,
                "end_sec": end,
                "text": text,
                "scores": scores,
                "total_score": round(total, 4),
            }
        )

    candidates.sort(key=lambda c: c["total_score"], reverse=True)
    # Ensure at least a few candidates
    if not candidates:
        candidates = [
            {
                "start_sec": 0,
                "end_sec": 20,
                "text": "Hook moment from source footage.",
                "scores": _score_text("Wait until you see this payoff.", campaign_name),
                "total_score": 50,
            }
        ]
    return candidates
