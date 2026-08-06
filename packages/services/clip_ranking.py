"""ClipRankingService — richer heuristic scores; render only top N."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from workers.clip_ranking.rank import rank_segments
from workers.clip_ranking.hooks import classify_hook
from workers.clip_ranking.llm_rank import LLMUnavailable, find_highlights


def _highlight_to_segment(h: dict[str, Any]) -> dict[str, Any]:
    """Adapt an LLM highlight into the segment shape the pipeline expects.

    The LLM gives one authoritative 0-100 viral score plus the hook line and a
    rationale. There are no sub-scores to fill the regex factor slots with, so
    they are seeded from the overall score and the real signal is carried in
    llm_score / hook_sentence / virality_reason.
    """
    score = float(h.get("score", 0))
    return {
        "start_sec": float(h["start_time"]),
        "end_sec": float(h["end_time"]),
        "text": h.get("hook_sentence") or h.get("title") or "",
        "scores": {
            "strong_opening": score,
            "curiosity": score,
            "conflict_surprise": score,
            "emotional_reaction": score,
            "clear_payoff": score,
            "standalone_clarity": score,
            "campaign_relevance": score,
        },
        "total_score": score,
        "llm_score": score,
        "llm_title": h.get("title"),
        "hook_sentence": h.get("hook_sentence"),
        "virality_reason": h.get("virality_reason"),
        "content_type": h.get("content_type"),
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
    # Which ranker produced this, and the LLM's output when it did.
    ranker: str = "regex"
    hook_sentence: str | None = None
    virality_reason: str | None = None

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
        min_sec: float = 15.0,
        max_sec: float = 25.0,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        # Prefer the LLM ranker. Keyword counting cannot tell an opinion bomb
        # from small talk — measured on a seeded transcript, the regex ranker
        # scored "Weather's been alright" above every substantive moment.
        ranker = "regex"
        llm_error: str | None = None
        raw: list[dict[str, Any]] = []

        # A heuristic transcript is placeholder text, not speech. Asking a model
        # to find viral moments in it burns API calls and latency to rank
        # nothing, and such clips are blocked from export anyway.
        if use_llm and (transcript or {}).get("engine") == "heuristic":
            use_llm = False
            llm_error = "skipped: transcript is placeholder text, not real speech"

        if use_llm:
            try:
                highlights = find_highlights(
                    transcript, want=select, min_sec=min_sec, max_sec=max_sec
                )
                raw = [_highlight_to_segment(h) for h in highlights]
                ranker = "llm"
            except LLMUnavailable as exc:
                llm_error = str(exc)
            except Exception as exc:  # noqa: BLE001 - never fail the pipeline on ranking
                llm_error = f"{type(exc).__name__}: {exc}"

        if not raw:
            # Degrade to keyword ranking rather than failing the run.
            raw = rank_segments(transcript, scenes, campaign_name=campaign_name)
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

            if seg.get("llm_score") is not None:
                # Trust the model's judgement. Re-deriving a score from the
                # stand-in sub-scores would just recover the same number, and
                # the dead-air proxy is meaningless for an LLM-chosen window.
                total = float(seg["llm_score"])
                if preferred_length_band and band == preferred_length_band:
                    total = min(100.0, total + 2)
                if preferred_hooks and hook_type in preferred_hooks:
                    total = min(100.0, total + 2)
            else:
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
                    e
                    for e in [
                        f"ranker={ranker}",
                        f"hook_type={hook_type}",
                        f"duration_band={band}",
                        f"words={words}",
                        seg.get("virality_reason"),
                    ]
                    if e
                ],
                ranker=ranker,
                hook_sentence=seg.get("hook_sentence"),
                virality_reason=seg.get("virality_reason"),
            )
            enriched = {
                **seg,
                "duration_band": band,
                "hook_type": hook_type,
                "rank_report": report.to_dict(),
                "total_score": total,
                "ranker": ranker,
            }
            reports.append(enriched)

        reports.sort(key=lambda r: r["total_score"], reverse=True)
        selected = reports[: max(3, min(select, len(reports)))]
        return {
            "candidates": reports,
            "selected": selected,
            "select_n": len(selected),
            "keep_n": len(reports),
            "ranker": ranker,
            "llm_error": llm_error,
            "note": "Only selected candidates should be rendered",
        }
