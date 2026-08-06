"""Campaign engine — eligibility, EV, top-N ranking for Operator Mode."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from packages.campaign_parser.scoring import expected_profit, score_campaign
from packages.shared_types.constants import DEFAULT_PRODUCTION_COST_PER_CLIP

# Below this stated approval rate a campaign is not worth working: at 3%, 97 of
# every 100 clips earn nothing regardless of how well they perform.
LOW_APPROVAL_REJECT = 0.20


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
    # None when CPM is unknown — no rate, no forecast.
    expected_profit: float | None
    is_eligible: bool
    reject_reasons: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    # Ceiling on total takeout from this campaign (per-clipper cap or remaining budget).
    max_earnings: float | None = None
    binding_limit: str | None = None
    views_to_cap: int | None = None

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
    historical_approval_rate: float | None = None,
    historical_avg_views: float | None = None,
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

        # A campaign-stated approval rate is hard evidence and outranks both the
        # 0.7 default and the operator's own history.
        stated_approval = item.get("approval_probability")
        base_approval = float(
            stated_approval
            if stated_approval is not None
            else (historical_approval_rate or 0.7)
        )
        base_views = float(item.get("expected_views", historical_avg_views or 10000))
        if (
            historical_approval_rate is not None
            and stated_approval is None
            and "approval_probability" not in item
        ):
            base_approval = 0.6 * 0.7 + 0.4 * historical_approval_rate
        if historical_avg_views is not None and "expected_views" not in item:
            base_views = 0.6 * 10000 + 0.4 * historical_avg_views

        result = score_campaign(
            cpm=item.get("cpm"),
            total_budget=total_budget,
            budget_utilised=utilised if total_budget else None,
            max_payout=item.get("max_payout"),
            campaign_age_days=item.get("campaign_age_days"),
            audience_match=float(item.get("audience_match_score", 70)),
            footage_quality=float(item.get("footage_quality_score", 70)),
            requirement_simplicity=float(item.get("requirement_simplicity_score", 70)),
            viral_potential=float(item.get("viral_potential_score", 70)),
            competition=float(item.get("competition_score", 50)),
            approval_probability=base_approval,
            expected_views=base_views,
            estimated_production_cost=float(
                item.get("estimated_production_cost", DEFAULT_PRODUCTION_COST_PER_CLIP)
            ),
            account_geos=account_geos,
            required_geo=item.get("required_geo") or [],
            has_rights=item.get("has_rights", True),
            unclear_instructions=item.get("unclear_instructions", False),
            requires_fake_engagement=item.get("requires_fake_engagement", False),
            misleading_content=item.get("misleading_content", False),
        )
        # Can this operator actually do the work? A high CPM on a UGC-only,
        # wrong-platform or gated campaign is worth nothing.
        from packages.campaign_parser.parser import capability_reject_reasons

        cap_text = f"{item.get('name') or ''}\n{item.get('brief_text') or ''}"
        cap_reasons = capability_reject_reasons(
            cap_text,
            operator_platforms=item.get("operator_platforms") or ["tiktok"],
            can_produce_ugc=bool(item.get("can_produce_ugc")),
        )
        if cap_reasons:
            result.is_recommended = False
            for r in cap_reasons:
                if r not in result.reject_reasons:
                    result.reject_reasons.append(r)

        # A campaign whose brief has not been read cannot be recommended. The
        # discover card carries a rate but defers the rules elsewhere, so its
        # numbers look strong precisely when the least is known about it - one
        # such campaign topped the ranking while actually requiring the operator
        # to film original content in Dutch for a Netherlands-only audience.
        if not item.get("brief_fetched"):
            result.is_recommended = False
            msg = "Brief not read yet - open the campaign and capture it before judging"
            if msg not in result.reject_reasons:
                result.reject_reasons.append(msg)
            # No verified rules means no basis for a per-clip forecast.
            result.expected_profit = None

        # A stated approval rate this low means most work is done for nothing,
        # whatever the CPM. Surfaced as a rejection so it cannot reach the top 3.
        if stated_approval is not None and stated_approval < LOW_APPROVAL_REJECT:
            result.is_recommended = False
            msg = (
                f"Campaign approves only {stated_approval:.0%} of submissions - "
                "most clips would earn nothing"
            )
            if msg not in result.reject_reasons:
                result.reject_reasons.append(msg)

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
                max_earnings=result.max_earnings,
                binding_limit=result.binding_limit,
                views_to_cap=result.views_to_cap,
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
