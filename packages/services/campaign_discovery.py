"""CampaignDiscoveryService — browser-assisted ingest (no CAPTCHA bypass)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from packages.campaign_parser.parser import parse_campaign_brief
from packages.services.campaign_scoring import CampaignScoringService


@dataclass
class DiscoveredCampaignDTO:
    external_id: str | None
    name: str
    brand: str | None = None
    external_url: str | None = None
    brief_text: str | None = None
    cpm: float | None = None
    total_budget: float | None = None
    budget_utilised: float | None = None
    budget_remaining_pct: float | None = None
    required_geo: list[str] = field(default_factory=list)
    required_hashtags: list[str] = field(default_factory=list)
    required_tags: list[str] = field(default_factory=list)
    asset_urls: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CampaignDiscoveryService:
    """
    Converts operator/extension payloads into structured campaign records.

    Does NOT log into Content Rewards, bypass CAPTCHA/MFA, or scrape without
    the user controlling the browser session.
    """

    def __init__(self, scoring: CampaignScoringService | None = None) -> None:
        self.scoring = scoring or CampaignScoringService()

    def normalize_item(self, item: dict[str, Any]) -> DiscoveredCampaignDTO:
        brief = item.get("brief_text") or item.get("name") or ""
        parsed = parse_campaign_brief(brief)
        return DiscoveredCampaignDTO(
            external_id=item.get("external_id"),
            name=item.get("name") or parsed.name,
            brand=item.get("brand") or parsed.brand,
            external_url=item.get("external_url"),
            brief_text=brief,
            cpm=item.get("cpm") if item.get("cpm") is not None else parsed.cpm,
            total_budget=item.get("total_budget") or parsed.total_budget,
            budget_utilised=item.get("budget_utilised") or parsed.budget_utilised,
            budget_remaining_pct=item.get("budget_remaining_pct"),
            required_geo=item.get("required_geo") or parsed.required_geo,
            required_hashtags=item.get("required_hashtags") or parsed.required_hashtags,
            required_tags=item.get("required_tags") or parsed.required_tags,
            asset_urls=list(item.get("asset_urls") or []),
            flags={
                "has_rights": item.get("has_rights", parsed.has_rights),
                "unclear_instructions": item.get(
                    "unclear_instructions", parsed.unclear_instructions
                ),
                "requires_fake_engagement": item.get(
                    "requires_fake_engagement", parsed.requires_fake_engagement
                ),
                "misleading_content": item.get(
                    "misleading_content", parsed.misleading_content
                ),
                "requires_logo": item.get("requires_logo", parsed.requires_logo),
                "requires_cta": item.get("requires_cta", parsed.requires_cta),
            },
            raw=item.get("raw") or {},
        )

    def detect_lifecycle(self, dto: DiscoveredCampaignDTO) -> dict[str, Any]:
        """Flag ending / low-budget / ineligible signals."""
        alerts: list[str] = []
        status = "available"
        pct = dto.budget_remaining_pct
        if pct is not None and pct <= 10:
            alerts.append("budget_nearly_exhausted")
            status = "ending_soon"
        if pct is not None and pct <= 0:
            alerts.append("budget_exhausted")
            status = "closed"
        if dto.flags.get("requires_fake_engagement") or dto.flags.get("misleading_content"):
            alerts.append("ineligible_policy")
            status = "ineligible"
        if not dto.flags.get("has_rights", True):
            alerts.append("no_rights")
            status = "ineligible"
        return {
            "lifecycle_status": status,
            "alerts": alerts,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    def enrich_with_score(
        self,
        dto: DiscoveredCampaignDTO,
        *,
        account_geos: list[str] | None = None,
        historical_approval_rate: float | None = None,
        historical_avg_views: float | None = None,
    ) -> dict[str, Any]:
        flags = dto.flags
        report = self.scoring.score(
            campaign_id=dto.external_id,
            cpm=dto.cpm,
            total_budget=dto.total_budget,
            budget_utilised=dto.budget_utilised,
            budget_remaining_pct=dto.budget_remaining_pct,
            account_geos=account_geos,
            required_geo=dto.required_geo,
            has_rights=flags.get("has_rights", True),
            unclear_instructions=flags.get("unclear_instructions", False),
            requires_fake_engagement=flags.get("requires_fake_engagement", False),
            misleading_content=flags.get("misleading_content", False),
            requirement_count=len(dto.required_hashtags) + len(dto.required_tags),
            requires_logo=flags.get("requires_logo", False),
            requires_cta=flags.get("requires_cta", False),
            historical_approval_rate=historical_approval_rate,
            historical_avg_views=historical_avg_views,
        )
        life = self.detect_lifecycle(dto)
        return {
            "campaign": dto.to_dict(),
            "score_report": report.to_dict(),
            "lifecycle": life,
        }
