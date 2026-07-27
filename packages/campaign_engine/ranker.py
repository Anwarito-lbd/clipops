"""Campaign engine — eligibility, EV, top-N ranking for Operator Mode."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from packages.campaign_parser.scoring import expected_profit, score_campaign


@dataclass
class RankedCampaign:
    external_id: str | None
    name: str
    brand: str | None
    cpm: float | None
    budget_remaining_pct: float | None
    difficulty: str  # Easy | Medium | Hard
    required_clips: int
    min_duration_sec: int
    max_duration_sec: int
    opportunity_score: float
    expected_profit: float
    is_eligible: bool
    reject_reasons: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_difficulty(
    *,
    requirement_count: int,
    min_duration: int,
    max_duration: int,
    requires_logo: bool,
    requires_cta: bool,
    forbidden_count: int,
) -> str:
    points = 0
    points += min(requirement_count, 6)
    if max_duration - min_duration < 15:
        points += 2
    if requires_logo:
        points += 2
    if requires_cta:
        points += 1
    points += min(forbidden_count, 3)
    if points <= 4:
        return "Easy"
    if points <= 8:
        return "Medium"
    return "Hard"


def check_eligibility(
    *,
    account_geos: list[str],
    required_geo: list[str],
    has_rights: bool,
    unclear: bool,
    fake_engagement: bool,
    misleading: bool,
    budget_utilisation: float | None,
    threshold: float = 0.90,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if required_geo and not (set(g.upper() for g in required_geo) & set(g.upper() for g in account_geos)):
        reasons.append("Required geography does not match your audience")
    if not has_rights:
        reasons.append("No rights to supplied material")
    if unclear:
        reasons.append("Instructions unclear or contradictory")
    if fake_engagement:
        reasons.append("Requires fake engagement")
    if misleading:
        reasons.append("Requires misleading content")
    if budget_utilisation is not None and budget_utilisation >= threshold:
        reasons.append(f"Budget nearly exhausted ({budget_utilisation:.0%})")
    return len(reasons) == 0, reasons


def rank_discovered_campaigns(
    items: list[dict[str, Any]],
    *,
    account_geos: list[str] | None = None,
    top_n: int = 3,
) -> list[RankedCampaign]:
    """Rank scraped/discovered campaigns; return best top_n eligible ones first, then rest."""
    account_geos = account_geos or ["US", "CA"]
    ranked: list[RankedCampaign] = []

    for item in items:
        total_budget = item.get("total_budget")
        utilised = item.get("budget_utilised") or 0
        utilisation = None
        remaining_pct = item.get("budget_remaining_pct")
        if remaining_pct is not None:
            utilisation = 1.0 - (float(remaining_pct) / 100.0)
        elif total_budget and total_budget > 0:
            utilisation = float(utilised) / float(total_budget)
            remaining_pct = round((1.0 - utilisation) * 100, 1)

        eligible, reasons = check_eligibility(
            account_geos=account_geos,
            required_geo=item.get("required_geo") or [],
            has_rights=item.get("has_rights", True),
            unclear=item.get("unclear_instructions", False),
            fake_engagement=item.get("requires_fake_engagement", False),
            misleading=item.get("misleading_content", False),
            budget_utilisation=utilisation,
        )

        result = score_campaign(
            cpm=item.get("cpm"),
            total_budget=total_budget,
            budget_utilised=utilised if total_budget else None,
            audience_match=float(item.get("audience_match_score", 70)),
            footage_quality=float(item.get("footage_quality_score", 70)),
            requirement_simplicity=float(item.get("requirement_simplicity_score", 70)),
            viral_potential=float(item.get("viral_potential_score", 70)),
            competition=float(item.get("competition_score", 50)),
            approval_probability=float(item.get("approval_probability", 0.7)),
            expected_views=float(item.get("expected_views", 10000)),
            estimated_production_cost=float(item.get("estimated_production_cost", 15)),
            account_geos=account_geos,
            required_geo=item.get("required_geo") or [],
            has_rights=item.get("has_rights", True),
            unclear_instructions=item.get("unclear_instructions", False),
            requires_fake_engagement=item.get("requires_fake_engagement", False),
            misleading_content=item.get("misleading_content", False),
        )
        if not eligible:
            result.is_recommended = False
            # merge unique reasons
            for r in reasons:
                if r not in result.reject_reasons:
                    result.reject_reasons.append(r)

        difficulty = estimate_difficulty(
            requirement_count=len(item.get("required_hashtags") or [])
            + len(item.get("required_tags") or []),
            min_duration=int(item.get("min_duration_sec") or 15),
            max_duration=int(item.get("max_duration_sec") or 60),
            requires_logo=bool(item.get("requires_logo")),
            requires_cta=bool(item.get("requires_cta")),
            forbidden_count=len(item.get("forbidden_words") or [])
            + len(item.get("forbidden_claims") or []),
        )

        ranked.append(
            RankedCampaign(
                external_id=item.get("external_id"),
                name=item.get("name") or "Untitled",
                brand=item.get("brand"),
                cpm=item.get("cpm"),
                budget_remaining_pct=remaining_pct,
                difficulty=difficulty,
                required_clips=int(item.get("required_clips") or 3),
                min_duration_sec=int(item.get("min_duration_sec") or 15),
                max_duration_sec=int(item.get("max_duration_sec") or 60),
                opportunity_score=result.score,
                expected_profit=result.expected_profit,
                is_eligible=result.is_recommended,
                reject_reasons=result.reject_reasons,
                raw=item,
            )
        )

    ranked.sort(
        key=lambda c: (not c.is_eligible, -c.opportunity_score, -(c.expected_profit or 0))
    )
    # Prefer returning top_n eligible; if fewer eligible, fill with next best
    eligible = [c for c in ranked if c.is_eligible][:top_n]
    if len(eligible) < top_n:
        rest = [c for c in ranked if c not in eligible]
        eligible.extend(rest[: top_n - len(eligible)])
    return eligible


def compute_ev(
    approval_probability: float,
    expected_views: float,
    cpm: float,
    production_cost: float,
) -> float:
    return expected_profit(approval_probability, expected_views, cpm, production_cost)
