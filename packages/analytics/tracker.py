"""Lightweight analytics — performance, earnings, learning hooks for Operator Mode."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def summarise_performance(posts: list[dict[str, Any]]) -> dict[str, Any]:
    by_style: dict[str, list[int]] = defaultdict(list)
    by_account: dict[str, list[int]] = defaultdict(list)
    for p in posts:
        views = int(p.get("views") or 0)
        by_style[p.get("style") or "unknown"].append(views)
        by_account[p.get("account") or "unknown"].append(views)

    def avg(xs: list[int]) -> float:
        return round(sum(xs) / len(xs), 1) if xs else 0.0

    return {
        "views_by_style": {k: avg(v) for k, v in by_style.items()},
        "views_by_account": {k: avg(v) for k, v in by_account.items()},
        "post_count": len(posts),
    }


def summarise_earnings(earnings: list[dict[str, Any]]) -> dict[str, Any]:
    provisional = sum(float(e.get("provisional_amount") or 0) for e in earnings)
    net = sum(float(e.get("net_amount") or 0) for e in earnings if e.get("net_amount") is not None)
    ready = sum(
        float(e.get("net_amount") or e.get("provisional_amount") or 0)
        for e in earnings
        if e.get("status") == "PAYOUT_READY"
    )
    return {
        "provisional_total": round(provisional, 4),
        "net_total": round(net, 4),
        "payout_ready_total": round(ready, 4),
        "count": len(earnings),
    }


def learning_hints(performance: dict[str, Any]) -> list[str]:
    """Phase-2-ready hints from observed averages (no model yet)."""
    hints: list[str] = []
    by_style = performance.get("views_by_style") or {}
    if by_style:
        best = max(by_style.items(), key=lambda kv: kv[1])
        hints.append(f"Highest average views so far: {best[0]} style ({best[1]})")
    if performance.get("post_count", 0) < 10:
        hints.append("Need more posts before the ranking engine can learn from your results")
    return hints
