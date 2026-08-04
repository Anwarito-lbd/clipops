"""Posting schedule: what to post, to which account, and when.

TikTok wants at least three hours between posts on the *same* account. That is
the whole reason posting splits into sittings: one clip to each account per
sitting yields comfortable gaps for free, so the operator touches the phone
three times a day rather than twelve.

Week one runs two sittings rather than three. The reason is measurement, not
caution - going straight to full volume spends source footage and per-campaign
caps on a hook formula that has never been checked against real views.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, time, timedelta, timezone
from typing import Any

# Hours chosen to satisfy the same-account gap, not audience activity. Once
# per-clip view data exists by posting hour, these should be re-derived.
FULL_SITTING_HOURS = (9, 13, 17)
RAMP_SITTING_HOURS = (9, 15)
RAMP_DAYS = 7
MIN_GAP_HOURS = 3


@dataclass
class ScheduledPost:
    clip_version_id: str
    account_id: str
    account_label: str
    caption: str
    hook_text: str | None
    campaign_name: str | None
    preview_url: str | None
    posted: bool = False
    submitted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Sitting:
    index: int
    at_hour: int
    label: str
    state: str  # done | now | upcoming
    posts: list[ScheduledPost] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "posts": [p.to_dict() for p in self.posts]}


def sitting_hours(days_active: int) -> tuple[int, ...]:
    """Two sittings during the ramp week, three afterwards."""
    return RAMP_SITTING_HOURS if days_active < RAMP_DAYS else FULL_SITTING_HOURS


def _state_for(hour: int, now: datetime, hours: tuple[int, ...]) -> str:
    if now.hour >= hour:
        # Still "now" until the following sitting comes due.
        later = [h for h in hours if h > hour]
        if not later or now.hour < later[0]:
            return "now"
        return "done"
    return "upcoming"


def build_schedule(
    *,
    ready_clips: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    days_active: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Lay approved clips onto today's sittings, one per account each time.

    Clips are dealt account-by-account so no account receives two posts in the
    same sitting, which is what keeps the three-hour gap intact by construction.
    """
    now = now or datetime.now(timezone.utc)
    hours = sitting_hours(days_active)
    if not accounts:
        return {
            "sittings": [],
            "unscheduled": len(ready_clips),
            "note": "No active accounts configured.",
        }

    # Group clips by the account they were rendered for, preserving order.
    by_account: dict[str, list[dict[str, Any]]] = {a["id"]: [] for a in accounts}
    unassigned: list[dict[str, Any]] = []
    for clip in ready_clips:
        aid = clip.get("account_id")
        if aid in by_account:
            by_account[aid].append(clip)
        else:
            unassigned.append(clip)

    # Spread anything unattributed across the emptiest accounts.
    for clip in unassigned:
        target = min(by_account, key=lambda k: len(by_account[k]))
        by_account[target].append(clip)

    label_by_id = {a["id"]: a.get("label") or a["id"][:8] for a in accounts}
    sittings: list[Sitting] = []
    for i, hour in enumerate(hours):
        s = Sitting(
            index=i + 1,
            at_hour=hour,
            label=f"{hour:02d}:00",
            state=_state_for(hour, now, hours),
        )
        for aid in by_account:
            if i < len(by_account[aid]):
                c = by_account[aid][i]
                s.posts.append(
                    ScheduledPost(
                        clip_version_id=c["id"],
                        account_id=aid,
                        account_label=label_by_id[aid],
                        caption=c.get("caption") or "",
                        hook_text=c.get("hook_text"),
                        campaign_name=c.get("campaign_name"),
                        preview_url=c.get("preview_url"),
                        posted=bool(c.get("posted")),
                        submitted=bool(c.get("submitted")),
                    )
                )
        sittings.append(s)

    scheduled = sum(len(s.posts) for s in sittings)
    leftover = max(0, len(ready_clips) - scheduled)

    next_up = next((s for s in sittings if s.state == "upcoming"), None)
    minutes_to_next = None
    if next_up:
        target = now.replace(hour=next_up.at_hour, minute=0, second=0, microsecond=0)
        minutes_to_next = max(0, int((target - now).total_seconds() // 60))

    return {
        "sittings": [s.to_dict() for s in sittings],
        "sitting_count": len(hours),
        "ramping": days_active < RAMP_DAYS,
        "days_active": days_active,
        "capacity_today": len(hours) * len(accounts),
        "scheduled": scheduled,
        "unscheduled": leftover,
        "next_sitting_in_minutes": minutes_to_next,
        "min_gap_hours": MIN_GAP_HOURS,
        "note": (
            f"Ramp week: {len(hours)} sittings/day. Full volume from day {RAMP_DAYS}."
            if days_active < RAMP_DAYS
            else f"{len(hours)} sittings/day, one clip per account each."
        ),
    }


def overdue_submissions(
    posts: list[dict[str, Any]], *, now: datetime | None = None, window_minutes: int = 60
) -> list[dict[str, Any]]:
    """Posts that are live but not yet submitted to the campaign.

    Campaigns expect the link within about an hour of posting, and a late
    submission can be refused outright - so this is the one backlog that costs
    money directly rather than merely delaying it.
    """
    now = now or datetime.now(timezone.utc)
    out = []
    for p in posts:
        if p.get("submitted"):
            continue
        posted_at = p.get("posted_at")
        if not posted_at:
            continue
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        mins = int((now - posted_at).total_seconds() // 60)
        out.append(
            {
                **p,
                "minutes_since_posted": mins,
                "overdue": mins > window_minutes,
            }
        )
    out.sort(key=lambda x: -x["minutes_since_posted"])
    return out
