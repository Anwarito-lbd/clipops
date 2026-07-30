from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str


class CampaignCreate(BaseModel):
    raw_brief: str
    external_url: Optional[str] = None
    footage_quality_score: float = 70
    requirement_simplicity_score: float = 70
    viral_potential_score: float = 70
    audience_match_score: float = 70
    competition_score: float = 50
    approval_probability: float = 0.7
    expected_views: float = 10000
    estimated_production_cost: float = 15


class CampaignOut(BaseModel):
    id: str
    name: str
    brand: Optional[str]
    external_url: Optional[str]
    status: str
    cpm: Optional[float]
    total_budget: Optional[float]
    budget_utilised: Optional[float]
    budget_remaining: Optional[float]
    score: Optional[float]
    expected_profit: Optional[float]
    is_recommended: bool
    reject_reasons: list[str]
    required_geo: list[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MarkJoinedRequest(BaseModel):
    pass


class AssetOut(BaseModel):
    id: str
    campaign_id: str
    filename: str
    storage_path: str
    status: str
    duration_sec: Optional[float]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class ClipVersionOut(BaseModel):
    id: str
    campaign_id: str
    style: str
    duration_band: str
    hook_variant: int
    subtitle_style: str
    caption: Optional[str]
    hook_text: Optional[str]
    status: str

    class Config:
        from_attributes = True


class ApproveRequest(BaseModel):
    override_reason: Optional[str] = None


class MarkPostedRequest(BaseModel):
    """Accept generic post_url; tiktok_url kept as alias for older clients."""

    post_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    notes: Optional[str] = None

    def resolved_url(self) -> str:
        url = (self.post_url or self.tiktok_url or "").strip()
        if not url:
            raise ValueError("post_url (or tiktok_url) is required")
        return url


class MarkSubmittedRequest(BaseModel):
    content_rewards_url: Optional[str] = None


class MetricsUpdate(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    metric_date: Optional[str] = None


class EarningsUpdate(BaseModel):
    provisional_amount: float
    mark_payout_ready: bool = False


class MarkPayoutReceived(BaseModel):
    notes: Optional[str] = None


class AccountUpsert(BaseModel):
    platform: str  # tiktok | youtube | content_rewards
    handle: str
    display_name: str
    style: Optional[str] = None
    audience_geo: list[str] = Field(default_factory=lambda: ["US", "CA"])
    audience_notes: Optional[str] = None
    preferred_clip_length: Optional[str] = None
    preferred_hooks: list[str] = Field(default_factory=list)
    is_active: bool = True


class ManualActionLinks(BaseModel):
    open_campaign: Optional[str] = None
    open_tiktok: str
    open_youtube: str = "https://studio.youtube.com"
    open_content_rewards: str
    note: str = (
        "AI assists; you Join / Post / Submit / Cash-out manually. "
        "Automated posting or engagement can result in a permanent ban."
    )


class HealthOut(BaseModel):
    status: str = "ok"
    product: str = "ClipOps"
    phase: str = "1"
    automation_boundary: str = "human_approval_manual_posting"
    env: str = "development"
    security_ok: bool = True
    security_messages: list[str] = Field(default_factory=list)
    media: dict[str, Any] = Field(default_factory=dict)
