"""Campaign expected-value and score engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from packages.shared_types.constants import (
    BUDGET_UTILISATION_REJECT_THRESHOLD,
    CPM_SCORE_CEILING,
    DEFAULT_PRODUCTION_COST_PER_CLIP,
    PLATFORM_FEE_MULTIPLIER,
    SCORE_WEIGHTS,
)


@dataclass
class ScoreResult:
    score: float
    # None when CPM is unknown — an unparsed rate must not read as a real forecast.
    expected_profit: float | None
    is_recommended: bool
    reject_reasons: list[str] = field(default_factory=list)
    factor_scores: dict[str, float] = field(default_factory=dict)
    budget_utilisation: float | None = None
    # Most you can take out of this campaign, and what bounds it.
    max_earnings: float | None = None
    binding_limit: str | None = None
    views_to_cap: int | None = None
    # Non-blocking data-quality notes (unlike reject_reasons, these don't veto).
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "expected_profit": self.expected_profit,
            "is_recommended": self.is_recommended,
            "reject_reasons": self.reject_reasons,
            "factor_scores": self.factor_scores,
            "budget_utilisation": self.budget_utilisation,
            "max_earnings": self.max_earnings,
            "binding_limit": self.binding_limit,
            "views_to_cap": self.views_to_cap,
            "warnings": self.warnings,
        }


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def expected_profit(
    approval_probability: float,
    expected_views: float,
    cpm: float,
    production_cost: float,
    fee_multiplier: float = PLATFORM_FEE_MULTIPLIER,
) -> float:
    return (
        approval_probability
        * (expected_views / 1000.0)
        * cpm
        * fee_multiplier
        - production_cost
    )


def campaign_ceiling(
    *,
    cpm: float | None,
    max_payout: float | None,
    budget_remaining: float | None,
    approval_probability: float = 0.7,
    fee_multiplier: float = PLATFORM_FEE_MULTIPLIER,
) -> dict[str, Any]:
    """Most you can realistically take out of one campaign.

    Content Rewards caps payout per clipper, so a campaign's worth is bounded by
    that cap — not by its CPM. Returns the binding limit and the views needed to
    reach it, which is what decides how many campaigns must run in parallel.
    """
    limits: list[tuple[str, float]] = []
    if max_payout is not None and max_payout > 0:
        limits.append(("per_clipper_cap", float(max_payout)))
    if budget_remaining is not None and budget_remaining > 0:
        limits.append(("campaign_budget", float(budget_remaining)))

    if not limits:
        return {
            "max_earnings": None,
            "binding_limit": None,
            "views_to_cap": None,
            "note": "No payout cap or remaining budget known — treat as unbounded.",
        }

    binding, ceiling = min(limits, key=lambda kv: kv[1])
    views_to_cap = None
    if cpm and cpm > 0:
        # earnings = views/1000 * cpm * fee * approval  ->  solve for views
        per_view = (cpm / 1000.0) * fee_multiplier * max(approval_probability, 0.01)
        if per_view > 0:
            views_to_cap = round(ceiling / per_view)
    return {
        "max_earnings": round(ceiling, 2),
        "binding_limit": binding,
        "views_to_cap": views_to_cap,
        "note": f"Capped at {ceiling:.2f} by {binding.replace('_', ' ')}.",
    }


def score_campaign(
    *,
    cpm: float | None,
    total_budget: float | None,
    budget_utilised: float | None,
    max_payout: float | None = None,
    audience_match: float = 70.0,
    footage_quality: float = 70.0,
    requirement_simplicity: float = 70.0,
    viral_potential: float = 70.0,
    competition: float = 50.0,
    approval_probability: float = 0.7,
    expected_views: float = 10_000,
    estimated_production_cost: float = DEFAULT_PRODUCTION_COST_PER_CLIP,
    account_geos: list[str] | None = None,
    required_geo: list[str] | None = None,
    has_rights: bool = True,
    eligibility_ok: bool = True,
    unclear_instructions: bool = False,
    requires_fake_engagement: bool = False,
    misleading_content: bool = False,
    tiktok_policy_risk: bool = False,
) -> ScoreResult:
    reasons: list[str] = []
    warnings: list[str] = []
    account_geos = account_geos or ["US", "CA"]
    required_geo = required_geo or []

    utilisation = None
    remaining_budget_score = 50.0
    if total_budget and total_budget > 0:
        used = budget_utilised or 0.0
        utilisation = used / total_budget
        remaining_budget_score = _clamp((1.0 - utilisation) * 100)
        if utilisation >= BUDGET_UTILISATION_REJECT_THRESHOLD:
            reasons.append(
                f"Campaign budget utilisation at {utilisation:.0%} "
                f"(>= {int(BUDGET_UTILISATION_REJECT_THRESHOLD * 100)}% close threshold)"
            )

    if not eligibility_ok:
        reasons.append("Accounts do not satisfy campaign eligibility rules")
    if required_geo:
        if not set(g.upper() for g in required_geo) & set(g.upper() for g in account_geos):
            reasons.append("Required geography does not match your real audience")
    if not has_rights:
        reasons.append("You do not have rights to the supplied material")
    if unclear_instructions:
        reasons.append("Campaign instructions are unclear or contradictory")
    if requires_fake_engagement:
        reasons.append("Campaign requires fake engagement")
    if misleading_content:
        reasons.append("Campaign requires misleading content")
    if tiktok_policy_risk:
        reasons.append("Required claims could violate TikTok rules")

    # An unknown CPM is not a zero CPM. Score it as neutral-low so it ranks below
    # a campaign with a known good rate, without pretending the rate is £0.
    if cpm is None:
        cpm_score = 25.0
        reasons_soft = "CPM could not be read from the brief — verify before committing"
    else:
        cpm_score = _clamp(100.0 * math.sqrt(min(cpm, CPM_SCORE_CEILING) / CPM_SCORE_CEILING))
        reasons_soft = None

    factor_scores = {
        "remaining_budget": remaining_budget_score,
        "cpm": cpm_score,
        "audience_match": _clamp(audience_match),
        "footage_quality": _clamp(footage_quality),
        "requirement_simplicity": _clamp(requirement_simplicity),
        "viral_potential": _clamp(viral_potential),
        "competition": _clamp(competition),
    }

    weighted = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        weighted += factor_scores[key] * (weight / 100.0)
    score = round(_clamp(weighted), 2)

    # No CPM means no forecast. A guessed profit reads as fact once it's on screen.
    if cpm is None:
        profit = None
    else:
        profit = round(
            expected_profit(
                approval_probability=approval_probability,
                expected_views=expected_views,
                cpm=cpm,
                production_cost=estimated_production_cost,
            ),
            4,
        )

    budget_remaining = None
    if total_budget and total_budget > 0:
        budget_remaining = total_budget - (budget_utilised or 0.0)

    ceiling = campaign_ceiling(
        cpm=cpm,
        max_payout=max_payout,
        budget_remaining=budget_remaining,
        approval_probability=approval_probability,
    )

    if reasons_soft:
        warnings.append(reasons_soft)
    if ceiling["max_earnings"] is not None:
        warnings.append(ceiling["note"])

    return ScoreResult(
        score=score,
        expected_profit=profit,
        is_recommended=len(reasons) == 0,
        reject_reasons=reasons,
        factor_scores=factor_scores,
        budget_utilisation=utilisation,
        max_earnings=ceiling["max_earnings"],
        binding_limit=ceiling["binding_limit"],
        views_to_cap=ceiling["views_to_cap"],
        warnings=warnings,
    )
