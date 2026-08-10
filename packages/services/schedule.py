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

# Default anchor, in UTC, matching FULL_SITTING_HOURS[0].
DEFAULT_ANCHOR = (9, 0)


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
    at_minute: int
    at_utc: str
    label: str
    state: str  # done | now | upcoming
    posts: list[ScheduledPost] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "posts": [p.to_dict() for p in self.posts]}


def sitting_hours(days_active: int) -> tuple[int, ...]:
    """Two sittings during the ramp week, three afterwards."""
    return RAMP_SITTING_HOURS if days_active < RAMP_DAYS else FULL_SITTING_HOURS


def parse_anchor(anchor: str | None) -> tuple[int, int]:
    """"HH:MM" -> (hour, minute). Falls back to the default on anything unusable."""
    if not anchor:
        return DEFAULT_ANCHOR
    try:
        h_s, _, m_s = anchor.partition(":")
        h, m = int(h_s), int(m_s or 0)
    except ValueError:
        return DEFAULT_ANCHOR
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return DEFAULT_ANCHOR
    return h, m


def sitting_datetimes(
    now: datetime,
    *,
    anchor: tuple[int, int],
    count: int,
    gap_hours: int = MIN_GAP_HOURS,
) -> list[datetime]:
    """Absolute times for today's sittings, starting at the anchor.

    Real datetimes rather than bare hour integers: a day anchored late enough
    runs its last sitting past midnight, and comparing `now.hour` to a sitting
    hour silently reorders the day when that happens.
    """
    start = now.replace(hour=anchor[0], minute=anchor[1], second=0, microsecond=0)
    return [start + timedelta(hours=gap_hours * i) for i in range(count)]


def _state_for(at: datetime, now: datetime, times: list[datetime]) -> str:
    if now < at:
        return "upcoming"
    # Still "now" until the following sitting comes due.
    later = [t for t in times if t > at]
    if not later or now < later[0]:
        return "now"
    return "done"


def build_schedule(
    *,
    ready_clips: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    days_active: int,
    now: datetime | None = None,
    anchor: str | None = None,
    sitting_count: int | None = None,
) -> dict[str, Any]:
    """Lay approved clips onto today's sittings, one per account each time.

    Clips are dealt account-by-account so no account receives two posts in the
    same sitting, which is what keeps the three-hour gap intact by construction.

    `anchor` ("HH:MM" UTC) pins the first sitting. Campaigns whose budget resets
    at a fixed time and closes once filled have to be posted into from the reset
    - a fixed 09:00 start would put every clip behind a day's competition.
    """
    now = now or datetime.now(timezone.utc)
    if anchor or sitting_count:
        count = sitting_count or len(sitting_hours(days_active))
        times = sitting_datetimes(now, anchor=parse_anchor(anchor), count=count)
    else:
        times = [
            now.replace(hour=h, minute=0, second=0, microsecond=0)
            for h in sitting_hours(days_active)
        ]
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
    for i, at in enumerate(times):
        s = Sitting(
            index=i + 1,
            at_hour=at.hour,
            at_minute=at.minute,
            at_utc=at.isoformat(),
            label=f"{at.hour:02d}:{at.minute:02d}",
            state=_state_for(at, now, times),
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

    next_idx = next((i for i, s in enumerate(sittings) if s.state == "upcoming"), None)
    minutes_to_next = None
    if next_idx is not None:
        minutes_to_next = max(0, int((times[next_idx] - now).total_seconds() // 60))

    return {
        "sittings": [s.to_dict() for s in sittings],
        "sitting_count": len(times),
        "ramping": days_active < RAMP_DAYS,
        "days_active": days_active,
        "capacity_today": len(times) * len(accounts),
        "scheduled": scheduled,
        "unscheduled": leftover,
        "next_sitting_in_minutes": minutes_to_next,
        "min_gap_hours": MIN_GAP_HOURS,
        "note": (
            f"Ramp week: {len(times)} sittings/day. Full volume from day {RAMP_DAYS}."
            if days_active < RAMP_DAYS and not (anchor or sitting_count)
            else f"{len(times)} sittings/day, one clip per account each."
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
