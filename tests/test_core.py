"""Unit tests for ClipOps core services — no network required."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.campaign_parser.parser import parse_campaign_brief
from packages.compliance_checker.checker import run_compliance_check
from packages.posting_queue.router import assert_versions_not_identical
from packages.services.campaign_scoring import CampaignScoringService
from packages.services.clip_ranking import ClipRankingService
from packages.services.forecast import ForecastService, PerformanceLearningService
from packages.shared_types.constants import ALLOWED_TRANSITIONS


def test_parse_brief_extracts_cpm_and_hashtags():
    brief = """VoltPop Push
CPM: $8.50
Budget: $25000 utilised 40%
Geo: US CA
Duration: 20-45 seconds
#VoltPop #ContentRewards @voltpop
Disclosure: Paid partnership
"""
    p = parse_campaign_brief(brief)
    assert p.cpm == 8.5
    assert "#VoltPop" in p.required_hashtags
    assert "@voltpop" in p.required_tags
    assert p.min_duration_sec == 20
    assert p.max_duration_sec == 45


def test_scoring_rejects_exhausted_budget():
    report = CampaignScoringService().score(
        cpm=5.0,
        total_budget=10000,
        budget_utilised=9500,
        requires_fake_engagement=False,
    )
    assert report.is_recommended is False
    assert report.recommendation == "AVOID"
    assert any("budget" in r.lower() or "90" in r for r in report.reject_reasons)
    assert report.explanations


def test_scoring_high_priority_shape():
    report = CampaignScoringService().score(
        campaign_id="c1",
        cpm=8.0,
        total_budget=50000,
        budget_utilised=5000,
        audience_match=90,
        footage_quality=85,
        viral_potential=88,
        requirement_simplicity=80,
        competition=40,
        approval_probability=0.75,
        expected_views=12000,
        estimated_production_cost=10,
        estimated_hours=0.4,
    )
    assert 0 <= report.score <= 100
    assert "factor_scores" in report.to_dict()
    assert report.estimated_profit_per_hour != 0 or report.score > 0


def test_compliance_requires_hashtags():
    result = run_compliance_check(
        campaign_name="VoltPop",
        expected_campaign_name="VoltPop",
        caption="hello world",
        required_hashtags=["#VoltPop"],
        required_tags=[],
        required_disclosure="Paid partnership",
        disclosure_in_video_start=True,
        duration_sec=30,
        min_duration_sec=15,
        max_duration_sec=60,
        aspect_ratio="9:16",
        forbidden_words=[],
        forbidden_claims=[],
        has_external_music=False,
        export_hash="abc",
        existing_hashes=[],
        requires_logo=False,
        has_logo=True,
        requires_cta=False,
        has_cta=True,
        posting_deadline=None,
    )
    assert result.passed is False
    assert any(c.key == "hashtags" and not c.passed for c in result.checks)


def test_duplicate_hash_detection():
    assert assert_versions_not_identical(["a", "b", "c"]) is True
    assert assert_versions_not_identical(["a", "a", "b"]) is False


def test_clip_ranking_selects_top_n():
    transcript = {
        "segments": [
            {"start": 0, "end": 8, "text": "Wait until you see this secret payoff."},
            {"start": 8, "end": 20, "text": "Here is why that changes everything."},
            {"start": 20, "end": 35, "text": "Normal filler content about nothing."},
        ]
    }
    scenes = {
        "scenes": [
            {"start_sec": 0, "end_sec": 8},
            {"start_sec": 8, "end_sec": 20},
            {"start_sec": 20, "end_sec": 35},
        ]
    }
    out = ClipRankingService().rank_footage(
        transcript, scenes, campaign_name="VoltPop", keep=20, select=3
    )
    assert out["select_n"] <= 3
    assert len(out["selected"]) <= 3
    assert out["selected"][0]["total_score"] >= out["selected"][-1]["total_score"]
    report = out["selected"][0]["rank_report"]
    assert "hook_score" in report
    assert report["predicted_performance"] in {"HIGH", "MEDIUM", "LOW"}


def test_forecast_required_clips():
    f = ForecastService().forecast(
        monthly_target=1000,
        currency="GBP",
        current_earnings=200,
        days_elapsed=10,
        days_in_month=30,
        approval_rate=0.7,
        avg_views_per_clip=8000,
        planning_cpm=2.0,
    )
    assert f.progress_pct == 20.0
    assert f.required_clips_per_day > 0
    assert f.currency == "GBP"


def test_learning_service_empty():
    out = PerformanceLearningService().analyse([])
    assert out["clip_count"] == 0
    assert out["ready_to_learn"] is False


def test_state_transitions_approve():
    assert "APPROVED" in ALLOWED_TRANSITIONS["REVIEW_REQUIRED"]
    assert "MANUALLY_POSTED" in ALLOWED_TRANSITIONS["EXPORTED"]
    assert "PAID" in ALLOWED_TRANSITIONS["PAYOUT_READY"]


def test_sanitize_upload_filename():
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.storage_security import assert_allowed_upload, sanitize_filename

    assert sanitize_filename("../../evil.mp4") == "evil.mp4"
    assert sanitize_filename("my clip!!.MOV") == "my_clip_.MOV"
    safe = assert_allowed_upload("ok.mp4", 1024, 10_000_000)
    assert safe.endswith(".mp4")
    try:
        assert_allowed_upload("note.txt", 10, 10_000_000)
        assert False, "should reject"
    except ValueError:
        pass


def test_compliance_unverified_logo_fails_when_required():
    result = run_compliance_check(
        campaign_name="VoltPop",
        expected_campaign_name="VoltPop",
        caption="Paid partnership #VoltPop",
        required_hashtags=["#VoltPop"],
        required_tags=[],
        required_disclosure="Paid partnership",
        disclosure_in_video_start=None,
        duration_sec=30,
        min_duration_sec=15,
        max_duration_sec=60,
        aspect_ratio="9:16",
        forbidden_words=[],
        forbidden_claims=[],
        has_external_music=False,
        export_hash="abc",
        existing_hashes=[],
        requires_logo=True,
        has_logo=None,
        requires_cta=False,
        has_cta=None,
        posting_deadline=None,
    )
    assert result.passed is False
    assert any(c.key == "logo" and not c.passed for c in result.checks)


def test_learning_priors_blend():
    priors = PerformanceLearningService().historical_priors(
        [
            {"views": 12000, "approval_status": "accepted", "editing_style": "dramatic"},
            {"views": 8000, "approval_status": "rejected", "editing_style": "dramatic"},
        ]
    )
    assert "historical_approval_rate" in priors
    assert priors["historical_approval_rate"] == 0.5
    assert priors["historical_avg_views"] == 10000.0


def test_ranker_accepts_historical_priors():
    from packages.campaign_engine.ranker import rank_discovered_campaigns

    items = [
        {
            "external_id": "1",
            "name": "A",
            "cpm": 5.0,
            "budget_remaining_pct": 80,
            "has_rights": True,
        }
    ]
    ranked = rank_discovered_campaigns(
        items,
        historical_approval_rate=0.9,
        historical_avg_views=20000,
    )
    assert ranked
    assert ranked[0].opportunity_score >= 0
