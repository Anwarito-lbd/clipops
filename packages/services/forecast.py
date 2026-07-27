"""Forecast + PerformanceLearningService for £1K month planning."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from packages.analytics.learning import cohort_averages, production_recommendations


@dataclass
class ForecastReport:
    currency: str
    monthly_target: float
    current_earnings: float
    progress_pct: float
    days_elapsed: int
    days_in_month: int
    monthly_run_rate: float
    projected_monthly_earnings: float
    clips_produced: int
    clips_posted: int
    clips_approved_est: int
    approval_rate: float
    avg_views_per_clip: float
    planning_cpm: float
    required_clips_per_day: float
    required_views_per_clip: float
    required_approval_rate: float
    on_track: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForecastService:
    def forecast(
        self,
        *,
        monthly_target: float = 1000.0,
        currency: str = "GBP",
        current_earnings: float = 0.0,
        days_elapsed: int = 1,
        days_in_month: int = 30,
        clips_produced: int = 0,
        clips_posted: int = 0,
        approval_rate: float = 0.7,
        avg_views_per_clip: float = 8210.0,
        planning_cpm: float = 2.0,
        platform_fee: float = 0.93,
        clips_per_day_capacity: float = 7.5,
    ) -> ForecastReport:
        days_elapsed = max(days_elapsed, 1)
        run_rate = (current_earnings / days_elapsed) * days_in_month
        projected = run_rate
        remaining = max(monthly_target - current_earnings, 0)
        days_left = max(days_in_month - days_elapsed, 1)

        # Revenue per approved clip at planning assumptions
        rev_per_approved = (avg_views_per_clip / 1000.0) * planning_cpm * platform_fee
        # Need approved clips for remaining target
        needed_approved = remaining / rev_per_approved if rev_per_approved > 0 else 0
        needed_posted = needed_approved / max(approval_rate, 0.01)
        required_per_day = needed_posted / days_left

        notes = [
            f"Planning CPM {currency} {planning_cpm:.2f} (not a guarantee).",
            f"Est. revenue/approved clip ≈ {currency} {rev_per_approved:.2f} at {avg_views_per_clip:.0f} views.",
            f"Capacity assumption {clips_per_day_capacity:.1f} clips/day across 3 accounts.",
        ]
        on_track = projected >= monthly_target * 0.9 or required_per_day <= clips_per_day_capacity
        if not on_track:
            notes.append(
                f"Need ~{required_per_day:.1f} posts/day to hit target — above capacity {clips_per_day_capacity}."
            )

        return ForecastReport(
            currency=currency,
            monthly_target=monthly_target,
            current_earnings=round(current_earnings, 2),
            progress_pct=round((current_earnings / monthly_target) * 100, 1) if monthly_target else 0,
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
            monthly_run_rate=round(run_rate, 2),
            projected_monthly_earnings=round(projected, 2),
            clips_produced=clips_produced,
            clips_posted=clips_posted,
            clips_approved_est=int(round(clips_posted * approval_rate)),
            approval_rate=approval_rate,
            avg_views_per_clip=avg_views_per_clip,
            planning_cpm=planning_cpm,
            required_clips_per_day=round(required_per_day, 2),
            required_views_per_clip=round(avg_views_per_clip, 0),
            required_approval_rate=0.70,
            on_track=on_track,
            notes=notes,
        )


class PerformanceLearningService:
    """Interpretable cohort learning — no heavy ML until n is large."""

    MIN_CLIPS = 50

    def analyse(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        cohorts = cohort_averages(rows)
        recs = production_recommendations(cohorts, min_n=5)
        ready = len(rows) >= self.MIN_CLIPS
        best = cohorts[0] if cohorts else None
        insight = None
        if best and best["n"] >= 5:
            conf = min(95, 40 + best["n"] * 4)
            insight = (
                f"{best['account']} | {best['editing_style']} | "
                f"{best['clip_length_band']} | hook={best['hook_type']} → "
                f"avg {best['avg_views']} views (n={best['n']}, confidence {conf}%)"
            )
        return {
            "clip_count": len(rows),
            "ready_to_learn": ready,
            "cohorts": cohorts[:25],
            "recommendations": recs,
            "top_insight": insight,
            "model": "interpretable_cohort_averages_v1",
        }

    def historical_priors(self, rows: list[dict[str, Any]], style: str | None = None) -> dict[str, float]:
        filtered = [r for r in rows if not style or r.get("editing_style") == style]
        if not filtered:
            return {}
        approvals = [
            r for r in filtered if (r.get("approval_status") or "").lower()
            in {"accepted", "earning", "paid", "approved"}
        ]
        rate = len(approvals) / len(filtered) if filtered else 0.7
        views = [float(r.get("views") or r.get("verified_views") or 0) for r in filtered]
        avg_views = sum(views) / len(views) if views else 0
        return {
            "historical_approval_rate": round(rate, 4),
            "historical_avg_views": round(avg_views, 1),
        }
