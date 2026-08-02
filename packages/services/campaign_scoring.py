"""CampaignScoringService — score 0–100 with explanations for Operator Mode."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from packages.campaign_parser.scoring import expected_profit, score_campaign
from packages.shared_types.constants import PLATFORM_FEE_MULTIPLIER, SCORE_WEIGHTS


@dataclass
class CampaignScoreReport:
    campaign_id: str | None
    score: float
    expected_cpm: float | None
    difficulty: str
    estimated_approval_rate: float
    estimated_views_per_clip: float
    # None when CPM is unknown — no rate, no forecast.
    estimated_profit_per_clip: float | None
    estimated_profit_per_hour: float | None
    recommendation: str  # HIGH_PRIORITY | CONSIDER | AVOID
    factor_scores: dict[str, float] = field(default_factory=dict)
    explanations: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    is_recommended: bool = False
    # Ceiling on what this campaign can pay you, and what bounds it.
    max_earnings: float | None = None
    binding_limit: str | None = None
    views_to_cap: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CampaignScoringService:
    """Data-driven campaign score with human-readable WHY."""

    def score(
        self,
        *,
        campaign_id: str | None = None,
        cpm: float | None = None,
        total_budget: float | None = None,
        budget_utilised: float | None = None,
        budget_remaining_pct: float | None = None,
        audience_match: float = 70.0,
        footage_quality: float = 70.0,
        requirement_simplicity: float = 70.0,
        viral_potential: float = 70.0,
        competition: float = 50.0,
        approval_probability: float = 0.7,
        expected_views: float = 10_000,
        estimated_production_cost: float = 15.0,
        estimated_hours: float = 0.5,
        account_geos: list[str] | None = None,
        required_geo: list[str] | None = None,
        has_rights: bool = True,
        unclear_instructions: bool = False,
        requires_fake_engagement: bool = False,
        misleading_content: bool = False,
        tiktok_policy_risk: bool = False,
        requirement_count: int = 0,
        min_duration_sec: int = 15,
        max_duration_sec: int = 60,
        requires_logo: bool = False,
        requires_cta: bool = False,
        forbidden_count: int = 0,
        historical_approval_rate: float | None = None,
        historical_avg_views: float | None = None,
    ) -> CampaignScoreReport:
        # Blend learning when available
        if historical_approval_rate is not None:
            approval_probability = 0.6 * approval_probability + 0.4 * historical_approval_rate
        if historical_avg_views is not None and historical_avg_views > 0:
            expected_views = 0.6 * expected_views + 0.4 * historical_avg_views

        utilised = budget_utilised
        if utilised is None and total_budget and budget_remaining_pct is not None:
            utilised = total_budget * (1.0 - budget_remaining_pct / 100.0)

        base = score_campaign(
            cpm=cpm,
            total_budget=total_budget,
            budget_utilised=utilised,
            audience_match=audience_match,
            footage_quality=footage_quality,
            requirement_simplicity=requirement_simplicity,
            viral_potential=viral_potential,
            competition=competition,
            approval_probability=approval_probability,
            expected_views=expected_views,
            estimated_production_cost=estimated_production_cost,
            account_geos=account_geos,
            required_geo=required_geo or [],
            has_rights=has_rights,
            unclear_instructions=unclear_instructions,
            requires_fake_engagement=requires_fake_engagement,
            misleading_content=misleading_content,
            tiktok_policy_risk=tiktok_policy_risk,
        )

        from packages.campaign_engine.ranker import estimate_difficulty

        difficulty = estimate_difficulty(
            requirement_count=requirement_count,
            min_duration=min_duration_sec,
            max_duration=max_duration_sec,
            requires_logo=requires_logo,
            requires_cta=requires_cta,
            forbidden_count=forbidden_count,
        )

        profit = base.expected_profit
        hours = max(estimated_hours, 0.1)
        profit_per_hour = round(profit / hours, 2) if profit is not None else None

        explanations: list[str] = []
        fs = base.factor_scores
        # Explain top positive / negative factors
        ordered = sorted(fs.items(), key=lambda kv: kv[1], reverse=True)
        for key, val in ordered[:3]:
            weight = SCORE_WEIGHTS.get(key, 0)
            explanations.append(f"+ {key.replace('_', ' ')}={val:.0f} (weight {weight})")
        for key, val in ordered[-2:]:
            if val < 55:
                explanations.append(f"- weak {key.replace('_', ' ')}={val:.0f}")
        if budget_remaining_pct is not None:
            explanations.append(f"Budget remaining ~{budget_remaining_pct:.0f}%")
        if cpm is not None:
            explanations.append(f"CPM/reward rate £{cpm:.2f} (fee-adjusted ×{PLATFORM_FEE_MULTIPLIER})")
        else:
            explanations.append("CPM unknown — could not be read from the brief")
        explanations.append(f"Difficulty={difficulty}; est. approval={approval_probability:.0%}")
        if profit is not None:
            explanations.append(
                f"EV ≈ approval×views/1000×CPM×{PLATFORM_FEE_MULTIPLIER} − cost = £{profit:.2f}/clip"
            )
        else:
            explanations.append("No EV estimate without a CPM — verify the rate on the campaign page")
        if base.max_earnings is not None:
            cap_note = f"Max you can take from this campaign ≈ £{base.max_earnings:.2f} ({base.binding_limit})"
            if base.views_to_cap:
                cap_note += f" — about {base.views_to_cap:,} views to reach it"
            explanations.append(cap_note)
        for w in base.warnings:
            explanations.append(f"! {w}")
        if historical_approval_rate is not None:
            explanations.append(
                f"Blended with your history (approval {historical_approval_rate:.0%})"
            )

        if not base.is_recommended:
            recommendation = "AVOID"
        elif base.score >= 85 and (profit_per_hour or 0) >= 25:
            recommendation = "HIGH_PRIORITY"
        elif base.score >= 70:
            recommendation = "CONSIDER"
        else:
            recommendation = "AVOID"

        for r in base.reject_reasons:
            explanations.append(f"REJECT: {r}")

        return CampaignScoreReport(
            campaign_id=campaign_id,
            score=base.score,
            expected_cpm=cpm,
            difficulty=difficulty,
            estimated_approval_rate=round(approval_probability, 4),
            estimated_views_per_clip=float(expected_views),
            estimated_profit_per_clip=round(profit, 4) if profit is not None else None,
            estimated_profit_per_hour=profit_per_hour,
            recommendation=recommendation,
            factor_scores=fs,
            explanations=explanations,
            reject_reasons=base.reject_reasons,
            is_recommended=base.is_recommended,
            max_earnings=base.max_earnings,
            binding_limit=base.binding_limit,
            views_to_cap=base.views_to_cap,
        )
