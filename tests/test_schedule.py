"""Posting schedule tests — sitting placement, not clip selection."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.services.schedule import build_schedule, parse_anchor, sitting_datetimes

ACCOUNTS = [
    {"id": "a1", "label": "TikTok 1"},
    {"id": "a2", "label": "TikTok 2"},
    {"id": "a3", "label": "TikTok 3"},
]


def _clips(n: int) -> list[dict]:
    return [{"id": f"c{i}", "caption": "", "account_id": ACCOUNTS[i % 3]["id"]} for i in range(n)]


def test_anchor_pins_the_first_sitting_to_the_budget_reset():
    """TJR resets at 11:30 EST (15:30 UTC); sitting one must land on it."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    out = build_schedule(
        ready_clips=_clips(9),
        accounts=ACCOUNTS,
        days_active=0,
        now=now,
        anchor="15:30",
        sitting_count=3,
    )
    assert [s["label"] for s in out["sittings"]] == ["15:30", "18:30", "21:30"]
    assert out["capacity_today"] == 9
    assert out["scheduled"] == 9


def test_anchor_overrides_the_ramp_week_reduction():
    """days_active=0 would otherwise yield two sittings and forfeit a third."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    out = build_schedule(
        ready_clips=_clips(9), accounts=ACCOUNTS, days_active=0,
        now=now, anchor="15:30", sitting_count=3,
    )
    assert out["sitting_count"] == 3


def test_sittings_past_midnight_stay_in_order():
    """A late anchor rolls into the next day; hour-integer compare reordered it."""
    times = sitting_datetimes(
        datetime(2026, 8, 7, 23, 0, tzinfo=timezone.utc), anchor=(22, 0), count=3
    )
    assert [t.strftime("%d %H:%M") for t in times] == ["07 22:00", "08 01:00", "08 04:00"]
    assert times == sorted(times)


def test_state_marks_exactly_one_sitting_current():
    now = datetime(2026, 8, 7, 19, 0, tzinfo=timezone.utc)
    out = build_schedule(
        ready_clips=_clips(9), accounts=ACCOUNTS, days_active=0,
        now=now, anchor="15:30", sitting_count=3,
    )
    states = [s["state"] for s in out["sittings"]]
    assert states == ["done", "now", "upcoming"]
    assert out["next_sitting_in_minutes"] == 150


def test_no_account_gets_two_posts_in_one_sitting():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    out = build_schedule(
        ready_clips=_clips(9), accounts=ACCOUNTS, days_active=0,
        now=now, anchor="15:30", sitting_count=3,
    )
    for sitting in out["sittings"]:
        ids = [p["account_id"] for p in sitting["posts"]]
        assert len(ids) == len(set(ids))


def test_default_schedule_is_unchanged_without_an_anchor():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    out = build_schedule(ready_clips=_clips(9), accounts=ACCOUNTS, days_active=30, now=now)
    assert [s["label"] for s in out["sittings"]] == ["09:00", "13:00", "17:00"]


def test_parse_anchor_falls_back_on_junk():
    assert parse_anchor("15:30") == (15, 30)
    assert parse_anchor("9") == (9, 0)
    assert parse_anchor("99:99") == (9, 0)
    assert parse_anchor(None) == (9, 0)
    assert parse_anchor("banana") == (9, 0)
