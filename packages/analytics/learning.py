"""Learning engine — aggregate clip_performance into production hints."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def cohort_averages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group by account + style + length + hook → avg views."""
    buckets: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        key = (
            r.get("account_label") or r.get("account_id") or "?",
            r.get("editing_style") or "?",
            r.get("clip_length_band") or "?",
            r.get("hook_type") or "?",
        )
        buckets[key].append(float(r.get("views") or r.get("verified_views") or 0))

    out = []
    for (account, style, length, hook), views in buckets.items():
        out.append(
            {
                "account": account,
                "editing_style": style,
                "clip_length_band": length,
                "hook_type": hook,
                "avg_views": round(sum(views) / len(views), 1) if views else 0,
                "n": len(views),
            }
        )
    out.sort(key=lambda x: x["avg_views"], reverse=True)
    return out


def production_recommendations(cohorts: list[dict[str, Any]], min_n: int = 5) -> list[str]:
    ready = [c for c in cohorts if c["n"] >= min_n]
    if not ready:
        total_n = sum(c["n"] for c in cohorts)
        return [
            f"Recorded {total_n} clip outcomes — need ~50–100 before auto-adjusting production.",
            "Keep logging views/earnings after each post.",
        ]
    best = ready[0]
    return [
        (
            f"Prefer {best['editing_style']} / {best['clip_length_band']}s / "
            f"hook={best['hook_type']} on {best['account']} "
            f"(avg {best['avg_views']} views across {best['n']} clips)"
        ),
        "Down-rank styles below median average views when selecting next top 3–5.",
    ]
