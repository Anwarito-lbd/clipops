"""Caption assembly — hashtags must survive, required tags must never be dropped."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.caption_generation.generate import generate_account_copy

BASE = dict(
    campaign_name="TJR August Campaign",
    excerpt="I lost $135,000 in a single day.",
    tags=[],
    disclosure="Paid partnership / Content Rewards",
    llm_hook="I lost $135,000 in a single day.",
    cta="LINK IN BIO: tjrtrades.com/get-blueprint",
)


def test_campaign_with_no_hashtags_still_gets_discovery_tags():
    out = generate_account_copy(style="commentary", hashtags=[], **BASE)
    tags = [w for w in out["caption"].split() if w.startswith("#")]
    assert tags, "a campaign stating no hashtags must not yield a bare caption"
    assert "#trading" in tags


def test_required_hashtags_are_never_displaced():
    out = generate_account_copy(
        style="dramatic", hashtags=["#TJRTrades", "#sponsored"], **BASE
    )
    tags = [w for w in out["caption"].split() if w.startswith("#")]
    assert tags[0] == "#TJRTrades"
    assert "#sponsored" in tags


def test_required_hashtags_are_not_duplicated_by_lane_tags():
    out = generate_account_copy(style="dramatic", hashtags=["#TRADING"], **BASE)
    tags = [w.lower() for w in out["caption"].split() if w.startswith("#")]
    assert tags.count("#trading") == 1


def test_filler_line_is_gone():
    out = generate_account_copy(style="commentary", hashtags=[], **BASE)
    assert "Thoughts below" not in out["caption"]


def test_hook_still_leads_and_cta_survives():
    out = generate_account_copy(style="commentary", hashtags=[], **BASE)
    assert out["caption"].startswith("I lost $135,000 in a single day.")
    assert "tjrtrades.com/get-blueprint" in out["caption"]
    assert "Paid partnership" in out["caption"]


def test_hashtags_sit_on_one_line():
    out = generate_account_copy(style="educational", hashtags=[], **BASE)
    tag_blocks = [b for b in out["caption"].split("\n\n") if b.strip().startswith("#")]
    assert len(tag_blocks) == 1
