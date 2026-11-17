"""Posting planner: turn the live leaderboard into a queue for two accounts with daily quotas.

Two lanes, never the same clip twice (platforms down-rank duplicate uploads, and ClipOps'
compliance gate forbids identical versions):

  FIRST lane (account A) — speed. The single best clip of each *fresh* moment (detected in the
                           last `first_max_age_seconds`, default 15 min) across all streamers,
                           posted as the draft the moment it scores above the cut-off. Once a
                           moment is stale, being first no longer matters, so it goes to lane B.
  BEST lane  (account B) — quality. Captioned finals, highest score first, rotating streamers and
                           moment types so the feed never repeats itself. Includes other streamers'
                           reactions to moments lane A already covered (different content, same hype).

"Same moment" = clips from different streamers detected within `same_moment_seconds` of each other
with the same moment category (everyone hits the opening cutscene at the same time on launch night).

Posting itself stays manual: `plan` recommends, you post, then `--mark` logs it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def _day(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))


def load_posted(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def mark_posted(path: Path, clip_id: str, account: str, *, streamer: str = "", now: float | None = None) -> dict:
    posted = load_posted(path)
    entry = {"clip_id": clip_id, "streamer": streamer, "account": account, "posted_at": now or time.time()}
    posted.append(entry)
    path.write_text(json.dumps(posted, indent=2), encoding="utf-8")
    return entry


def group_moments(rows: list[dict], same_moment_seconds: float = 90.0) -> list[list[dict]]:
    """Cluster clips of the same moment across streamers (same category, detected close together)."""
    groups: list[list[dict]] = []
    for r in sorted(rows, key=lambda r: r.get("detected_at") or 0):
        for g in groups:
            head = g[0]
            if (r.get("moment") and r.get("moment") == head.get("moment")
                    and r.get("streamer") != head.get("streamer")
                    and abs((r.get("detected_at") or 0) - (head.get("detected_at") or 0)) <= same_moment_seconds
                    and all(x.get("streamer") != r.get("streamer") for x in g)):
                g.append(r)
                break
        else:
            groups.append([r])
    for g in groups:
        g.sort(key=lambda r: r.get("score") or 0, reverse=True)
    return groups


def plan_posts(
    rows: list[dict],
    posted: list[dict],
    *,
    accounts: tuple[str, str] = ("A", "B"),
    per_account_per_day: int = 10,
    first_min_score: float = 60.0,
    best_min_score: float = 45.0,
    same_moment_seconds: float = 90.0,
    first_max_age_seconds: float = 900.0,
    allow_spoilers: bool = False,
    now: float | None = None,
) -> dict:
    now = now or time.time()
    today = _day(now)
    done = {p["clip_id"] for p in posted}
    used_today = {a: sum(1 for p in posted if p["account"] == a and _day(p["posted_at"]) == today) for a in accounts}
    left = {a: max(0, per_account_per_day - used_today[a]) for a in accounts}

    pool = [r for r in rows if r.get("clip") or r.get("draft")]
    if not allow_spoilers:
        pool = [r for r in pool if not r.get("spoiler_risk")]
    groups = group_moments(pool, same_moment_seconds)
    first_acc, best_acc = accounts

    # Lane A: one clip per moment — the best — if any clip of that moment was already posted, skip.
    first: list[dict] = []
    taken: set[str] = set(done)
    for g in sorted(groups, key=lambda g: g[0].get("detected_at") or 0, reverse=True):
        if any(r["clip_id"] in done for r in g):
            continue
        top = g[0]
        fresh = now - (top.get("detected_at") or 0) <= first_max_age_seconds
        if fresh and (top.get("score") or 0) >= first_min_score:
            first.append({**top, "account": first_acc, "post": "draft" if not top.get("clip") else "final",
                          "same_moment_streamers": [r.get("streamer") for r in g[1:]]})
    first.sort(key=lambda r: r.get("score") or 0, reverse=True)
    first = first[: left[first_acc]]
    taken |= {r["clip_id"] for r in first}

    # Lane B: best remaining captioned finals, rotating streamer + moment type.
    candidates = [r for r in pool if r["clip_id"] not in taken and r.get("clip") and r.get("final")
                  and (r.get("score") or 0) >= best_min_score]
    candidates.sort(key=lambda r: r.get("score") or 0, reverse=True)
    best: list[dict] = []
    last_streamer = last_moment = None
    while candidates and len(best) < left[best_acc]:
        pick = next((r for r in candidates if r.get("streamer") != last_streamer and r.get("moment") != last_moment),
                    None) or candidates[0]
        candidates.remove(pick)
        best.append({**pick, "account": best_acc, "post": "final"})
        last_streamer, last_moment = pick.get("streamer"), pick.get("moment")

    return {
        "day": today,
        "quota_left": left,
        "first_lane": first,
        "best_lane": best,
        "held_for_spoilers": [r["clip_id"] for r in rows if r.get("spoiler_risk")] if not allow_spoilers else [],
    }
