"""Campaign expected-value and score engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.shared_types.constants import (
    BUDGET_UTILISATION_REJECT_THRESHOLD,
    PLATFORM_FEE_MULTIPLIER,
    SCORE_WEIGHTS,
)


@dataclass
class ScoreResult:
    score: float
    expected_profit: float
    is_recommended: bool
    reject_reasons: list[str] = field(default_factory=list)
    factor_scores: dict[str, float] = field(default_factory=dict)
    budget_utilisation: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "expected_profit": self.expected_profit,
            "is_recommended": self.is_recommended,
            "reject_reasons": self.reject_reasons,
            "factor_scores": self.factor_scores,
            "budget_utilisation": self.budget_utilisation,
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


def score_campaign(
    *,
    cpm: float | None,
    total_budget: float | None,
    budget_utilised: float | None,
    audience_match: float = 70.0,
    footage_quality: float = 70.0,
    requirement_simplicity: float = 70.0,
    viral_potential: float = 70.0,
    competition: float = 50.0,
    approval_probability: float = 0.7,
    expected_views: float = 10_000,
    estimated_production_cost: float = 15.0,
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

    cpm_value = cpm or 0.0
    # Map CPM roughly: $0 → 0, $5 → 50, $15+ → 100
    cpm_score = _clamp((cpm_value / 15.0) * 100)

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

    profit = expected_profit(
        approval_probability=approval_probability,
        expected_views=expected_views,
        cpm=cpm_value,
        production_cost=estimated_production_cost,
    )

    return ScoreResult(
        score=score,
        expected_profit=round(profit, 4),
        is_recommended=len(reasons) == 0,
        reject_reasons=reasons,
        factor_scores=factor_scores,
        budget_utilisation=utilisation,
    )
