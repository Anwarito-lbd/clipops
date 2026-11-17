"""Rank clips so you post the *best* moments, not just every chat spike.

Score (0-100) combines what actually predicts a great stream clip:

  chat velocity   22  how many times above normal chat went (ratio vs baseline)
  chat intensity   8  how statistically extreme it was (robust z-score)
  sustain         18  how long chat stayed elevated afterwards (big moments keep chat going)
  volume          10  total reaction messages (log scale)
  hype            10  share of reaction messages that are hype ("LETS GO", "HE DID NOT", "clip it")
  audio           14  loudness jump in the clip (streamer yelling, crowd, explosion)
  speech           8  excited / hook-y speech in the Whisper transcript
  moment          10  game-profile prior for the moment type (GTA 6: chase/glitch > story)

Sustain is only final once chat calms down, so live scores are refined as more buckets close.
"""

from __future__ import annotations

import math
import re
import statistics
import subprocess
from pathlib import Path

WEIGHTS = {
    "chat_velocity": 22, "chat_intensity": 8, "sustain": 18, "volume": 10,
    "hype": 10, "audio": 14, "speech": 8, "moment": 10,
}
assert sum(WEIGHTS.values()) == 100
EXCITED = re.compile(
    r"\b(wait|no way|oh my|what|holy|insane|crazy|let'?s go|did not|didn'?t|never|wow|bro|yes+|no+)\b|!", re.I
)
_M_RE = re.compile(r"\bM:\s*(-?\d+(?:\.\d+)?)")


def audio_excitement(video: str | Path, *, ffmpeg: str = "ffmpeg") -> dict:
    """EBU R128 momentary loudness over the clip: peak jump above the clip's median, in dB."""
    try:
        res = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "ebur128=framelog=verbose", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"jump_db": 0.0, "peak_at": None, "ok": False}
    vals = [float(v) for v in _M_RE.findall(res.stderr)]
    vals = [v for v in vals if v > -70]  # drop silence / meter warm-up
    if len(vals) < 10:
        return {"jump_db": 0.0, "peak_at": None, "ok": False}
    med = statistics.median(vals)
    # p95 instead of max so a single click doesn't win
    p95 = sorted(vals)[int(0.95 * (len(vals) - 1))]
    peak_idx = max(range(len(vals)), key=vals.__getitem__)
    return {"jump_db": round(p95 - med, 2), "median_lufs": round(med, 1), "peak_at": round(peak_idx * 0.1, 1), "ok": True}


def speech_excitement(captions: list[dict] | None) -> float:
    if not captions:
        return 0.3  # neutral: no speech engine / silent gameplay shouldn't sink a clip
    text = " ".join(c["text"] for c in captions)
    dur = max(1.0, captions[-1]["end"] - captions[0]["start"])
    wps = len(text.split()) / dur
    hits = len(EXCITED.findall(text))
    return round(min(1.0, 0.5 * min(1.0, hits / 4) + 0.5 * min(1.0, max(0.0, wps - 1.5) / 2.0)), 3)


def score_clip(
    spike: dict, sustain: dict, audio: dict, captions: list[dict] | None, moment_weight: float = 0.3
) -> dict:
    ratio = max(1.0, float(spike.get("ratio", 1.0)))
    comps = {
        "chat_velocity": min(1.0, math.log2(ratio) / 4.0),  # 16x normal chat -> full marks
        "chat_intensity": min(1.0, float(spike.get("zscore", 0.0)) / 20.0),
        "sustain": min(1.0, float(sustain.get("seconds", 0.0)) / 40.0),
        "volume": min(1.0, math.log10(max(1, int(sustain.get("messages") or spike.get("count", 1)))) / 3.0),
        "hype": min(1.0, float(spike.get("hype_ratio", 0.0)) / 0.6),
        "audio": min(1.0, max(0.0, float(audio.get("jump_db", 0.0)) - 3.0) / 12.0) if audio.get("ok") else 0.3,
        "speech": speech_excitement(captions),
        "moment": max(0.0, min(1.0, float(moment_weight))),
    }
    total = sum(WEIGHTS[k] * v for k, v in comps.items())
    return {
        "score": round(total, 1),
        "components": {k: round(v, 3) for k, v in comps.items()},
        "final": bool(sustain.get("final")),
    }


def suggested_caption(
    captions: list[dict] | None, top_terms: list[str], audio_peak_at: float | None,
    top_messages: list[str] | None = None,
) -> str:
    """A post-ready hook line: the spoken line at the loudness peak, else chat's most-spammed reaction."""
    if captions:
        if audio_peak_at is not None:
            near = min(captions, key=lambda c: abs((c["start"] + c["end"]) / 2 - audio_peak_at))
            if near["text"].strip():
                return near["text"].strip().upper()
        excited = [c["text"] for c in captions if EXCITED.search(c["text"])]
        if excited:
            return excited[-1].strip().upper()
    for msg in top_messages or []:
        if len(msg.split()) >= 2:  # a real phrase ("SWAT INCOMING") beats single emotes
            return msg
    terms = [t for t in top_terms if len(t) > 1][:3]
    return (" ".join(terms) + "?!") if terms else "YOU HAVE TO SEE THIS"


def leaderboard(clips: list[dict]) -> list[dict]:
    ok = [c for c in clips if c.get("status") != "FAILED"]
    ranked = sorted(ok, key=lambda c: c.get("rank", {}).get("score", 0.0), reverse=True)
    out = []
    for i, c in enumerate(ranked, 1):
        out.append({
            "position": i,
            "clip_id": c["clip_id"],
            "score": c.get("rank", {}).get("score"),
            "final": c.get("rank", {}).get("final"),
            "window": c.get("window"),
            "streamer": c.get("streamer"),
            "moment": (c.get("moment") or {}).get("category"),
            "spoiler_risk": (c.get("moment") or {}).get("spoiler_risk"),
            "title": (c.get("post") or {}).get("title"),
            "hook": (c.get("post") or {}).get("hook"),
            "clip": (c.get("files") or {}).get("clip"),
            "draft": (c.get("files") or {}).get("draft"),
            "detected_at": (c.get("spike") or {}).get("detected_at"),
            "seconds_spike_to_draft": c.get("latency", {}).get("spike_to_draft"),
        })
    return out
