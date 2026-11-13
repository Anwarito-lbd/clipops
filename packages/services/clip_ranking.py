"""ClipRankingService — richer heuristic scores; render only top N."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from workers.clip_ranking.rank import rank_segments
from workers.clip_ranking.hooks import classify_hook


def compute_retention_pacing(
    text: str,
    duration_sec: float,
    *,
    word_segments: list[dict[str, Any]] | None = None,
    start_sec: float = 0.0,
    end_sec: float | None = None,
) -> dict[str, Any]:
    """Compute deterministic short-form retention pacing metrics for a candidate window."""
    dur = max(0.5, float(duration_sec))
    words_list = (text or "").split()
    word_count = len(words_list)
    wpm = round((word_count / dur) * 60.0, 1)

    # Estimate spoken coverage vs dead air using word_segments if available, else 0.35s/word
    spoken_sec = 0.0
    hook_words_3s = 0
    window_end = end_sec if end_sec is not None else start_sec + dur
    if word_segments:
        for w in word_segments:
            ws = float(w.get("start", 0.0))
            we = float(w.get("end", ws + 0.3))
            if we >= start_sec and ws <= window_end:
                overlap = max(0.0, min(we, window_end) - max(ws, start_sec))
                spoken_sec += overlap
                if ws < start_sec + 3.0:
                    hook_words_3s += 1
        spoken_sec = min(dur, spoken_sec)
    else:
        spoken_sec = min(dur, word_count * 0.35)
        hook_words_3s = min(word_count, max(1, round((word_count / dur) * 3.0))) if word_count else 0

    dead_air_sec = round(max(0.0, dur - spoken_sec), 2)
    dead_air_ratio = round(dead_air_sec / dur, 3)

    if 125.0 <= wpm <= 185.0:
        pacing_label = "OPTIMAL_CADENCE"
    elif wpm > 185.0:
        pacing_label = "FAST_ENERGETIC"
    elif wpm >= 75.0:
        pacing_label = "MODERATE"
    else:
        pacing_label = "SPARSE_LOW_SPEECH"

    return {
        "word_count": word_count,
        "duration_sec": round(dur, 2),
        "wpm": wpm,
        "ideal_wpm_range": [125, 185],
        "spoken_sec": round(spoken_sec, 2),
        "dead_air_sec": dead_air_sec,
        "dead_air_ratio": dead_air_ratio,
        "hook_window_words_3s": hook_words_3s,
        "pacing_label": pacing_label,
    }


@dataclass
class ClipRankReport:
    clip_id: str | None
    score: float
    hook_score: float
    emotion_score: float
    payoff_score: float
    campaign_fit: float
    curiosity_score: float
    conflict_score: float
    clarity_score: float
    duration_score: float
    dead_air_penalty: float
    predicted_performance: str  # HIGH | MEDIUM | LOW
    hook_type: str
    explanations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClipRankingService:
    def rank_footage(
        self,
        transcript: dict[str, Any],
        scenes: dict[str, Any],
        *,
        campaign_name: str,
        keep: int = 20,
        select: int = 5,
        preferred_length_band: str | None = None,
        preferred_hooks: list[str] | None = None,
    ) -> dict[str, Any]:
        raw = rank_segments(transcript, scenes, campaign_name=campaign_name)
        word_segments = transcript.get("word_segments") or []
        reports: list[dict[str, Any]] = []
        for i, seg in enumerate(raw[:keep]):
            scores = seg.get("scores") or {}
            duration = float(seg["end_sec"]) - float(seg["start_sec"])
            # Duration preference
            if duration <= 25:
                band = "15-25"
                duration_score = 80.0
            elif duration <= 40:
                band = "25-40"
                duration_score = 90.0
            else:
                band = "40-60"
                duration_score = 70.0
            if preferred_length_band and band == preferred_length_band:
                duration_score = min(100.0, duration_score + 10)

            hook_type = classify_hook(seg.get("text") or "")
            hook_boost = 8.0 if preferred_hooks and hook_type in preferred_hooks else 0.0

            # Dead-air proxy: very short text vs long window
            words = len((seg.get("text") or "").split())
            dead_air = max(0.0, 40.0 - words * 2) if duration > 10 else 0.0

            hook_score = float(scores.get("strong_opening", 50)) + hook_boost
            emotion = float(scores.get("emotional_reaction", 50))
            payoff = float(scores.get("clear_payoff", 50))
            fit = float(scores.get("campaign_relevance", 50))
            curiosity = float(scores.get("curiosity", 50))
            conflict = float(scores.get("conflict_surprise", 50))
            clarity = float(scores.get("standalone_clarity", 50))

            total = (
                hook_score * 0.18
                + curiosity * 0.12
                + conflict * 0.12
                + emotion * 0.12
                + payoff * 0.18
                + clarity * 0.12
                + fit * 0.10
                + duration_score * 0.06
            ) - dead_air * 0.05
            total = round(max(0.0, min(100.0, total)), 2)

            if total >= 80:
                pred = "HIGH"
            elif total >= 60:
                pred = "MEDIUM"
            else:
                pred = "LOW"

            report = ClipRankReport(
                clip_id=f"cand-{i+1}",
                score=total,
                hook_score=round(hook_score, 1),
                emotion_score=round(emotion, 1),
                payoff_score=round(payoff, 1),
                campaign_fit=round(fit, 1),
                curiosity_score=round(curiosity, 1),
                conflict_score=round(conflict, 1),
                clarity_score=round(clarity, 1),
                duration_score=round(duration_score, 1),
                dead_air_penalty=round(dead_air, 1),
                predicted_performance=pred,
                hook_type=hook_type,
                explanations=[
                    f"hook_type={hook_type}",
                    f"duration_band={band}",
                    f"words={words}",
                ],
            )
            pacing = compute_retention_pacing(
                seg.get("text") or "",
                duration,
                word_segments=word_segments,
                start_sec=float(seg["start_sec"]),
                end_sec=float(seg["end_sec"]),
            )
            enriched = {
                **seg,
                "duration_band": band,
                "hook_type": hook_type,
                "retention_pacing": pacing,
                "rank_report": report.to_dict(),
                "total_score": total,
            }
            reports.append(enriched)

        reports.sort(key=lambda r: r["total_score"], reverse=True)
        selected = reports[: max(3, min(select, len(reports)))]
        return {
            "candidates": reports,
            "selected": selected,
            "select_n": len(selected),
            "keep_n": len(reports),
            "note": "Only selected candidates should be rendered",
        }
