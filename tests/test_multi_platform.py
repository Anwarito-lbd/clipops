"""Tests for multi-platform accounts, Scrapling normalize, TTS commentary helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.posting_queue.router import build_posting_packages
from packages.services.scrapling_cr import normalize_scraped_item, parse_discover_html
from packages.shared_types.accounts import default_seed_rows, slot_map_for_accounts
from workers.video_rendering.tts_commentary import commentary_script


def test_seed_rows_include_six_posting_accounts():
    rows = default_seed_rows()
    platforms = [r["platform"] for r in rows]
    assert platforms.count("tiktok") == 3
    assert platforms.count("youtube") == 3
    assert platforms.count("content_rewards") == 1


def test_slot_map_supports_six_accounts():
    class A:
        def __init__(self, i):
            self.id = f"id-{i}"

    accounts = [A(i) for i in range(6)]
    m = slot_map_for_accounts(accounts)
    assert m["id-0"] == 1
    assert m["id-5"] == 6


def test_build_posting_packages_multi_platform():
    versions = [
        {
            "id": "v1",
            "campaign_id": "c1",
            "style": "dramatic",
            "caption": "Paid partnership #Test",
            "social_account_id": "a1",
            "platform": "tiktok",
        },
        {
            "id": "v2",
            "campaign_id": "c1",
            "style": "dramatic",
            "caption": "Paid partnership #Test",
            "social_account_id": "a2",
            "platform": "youtube",
        },
    ]
    meta = {
        "a1": {"slot": 1, "label": "TikTok — Dramatic", "platform": "tiktok", "open_url": "https://www.tiktok.com"},
        "a2": {
            "slot": 2,
            "label": "YouTube — Dramatic",
            "platform": "youtube",
            "open_url": "https://studio.youtube.com",
        },
    }
    pkgs = build_posting_packages(versions, [], {}, account_meta=meta)
    assert len(pkgs) == 2
    assert pkgs[0].platform == "tiktok"
    assert pkgs[1].platform == "youtube"
    assert pkgs[1].open_url.endswith("youtube.com")


def test_scrapling_normalize_and_html_parse():
    item = normalize_scraped_item({"name": "Brand X", "reward_text": "$5.50 /1k", "url": "https://example.com/c/1"})
    assert item["name"] == "Brand X"
    assert item["cpm"] == 5.5
    html = '<a href="/content-rewards/foo">Foo Campaign $4</a>'
    parsed = parse_discover_html(html, base_url="https://whop.com/")
    assert any("Foo" in (p["name"] or "") for p in parsed)


def test_commentary_tts_script_uses_hook():
    s = commentary_script(hook_text="Okay but can we talk about this?", campaign_name="VoltPop")
    assert "talk about this" in s.lower()
