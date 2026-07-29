from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from app.auth import authenticate_operator, create_access_token, require_operator
from app.config import get_settings
from app.db import Campaign, CampaignRequirement, SocialAccount, get_db
from app.schemas import (
    AccountUpsert,
    CampaignCreate,
    CampaignOut,
    LoginRequest,
    ManualActionLinks,
    TokenResponse,
)
from packages.campaign_parser.parser import parse_campaign_brief
from packages.campaign_parser.scoring import score_campaign
from packages.shared_types.accounts import POSTING_PLATFORMS, merge_audience_geos

router = APIRouter(tags=["campaigns"])


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not authenticate_operator(body.email, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(body.email))


@router.get("/manual-links", response_model=ManualActionLinks)
def manual_links(campaign_url: str | None = None, _user: str = Depends(require_operator)) -> ManualActionLinks:
    settings = get_settings()
    return ManualActionLinks(
        open_campaign=campaign_url,
        open_tiktok=settings.tiktok_url,
        open_youtube=settings.youtube_url,
        open_content_rewards=settings.content_rewards_url,
    )


def _serialize_account(r: SocialAccount) -> dict:
    return {
        "id": r.id,
        "platform": r.platform,
        "handle": r.handle,
        "display_name": r.display_name,
        "style": r.style,
        "audience_geo": r.audience_geo,
        "audience_notes": r.audience_notes,
        "preferred_clip_length": r.preferred_clip_length,
        "preferred_hooks": r.preferred_hooks or [],
        "is_active": r.is_active,
    }


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = db.query(SocialAccount).order_by(SocialAccount.platform, SocialAccount.handle).all()
    return [_serialize_account(r) for r in rows]


@router.post("/accounts")
def upsert_account(
    body: AccountUpsert,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    platform = body.platform.strip().lower()
    if platform not in (*POSTING_PLATFORMS, "content_rewards"):
        raise HTTPException(400, f"platform must be one of tiktok, youtube, content_rewards")
    row = (
        db.query(SocialAccount)
        .filter(SocialAccount.platform == platform, SocialAccount.handle == body.handle)
        .first()
    )
    if row is None:
        row = SocialAccount(platform=platform, handle=body.handle)
        db.add(row)
    row.display_name = body.display_name
    row.style = body.style
    row.audience_geo = body.audience_geo
    row.audience_notes = body.audience_notes
    row.preferred_clip_length = body.preferred_clip_length
    row.preferred_hooks = body.preferred_hooks
    row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return _serialize_account(row)


@router.patch("/accounts/{account_id}")
def patch_account(
    account_id: str,
    body: AccountUpsert,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    row = db.get(SocialAccount, account_id)
    if not row:
        raise HTTPException(404, "Account not found")
    row.platform = body.platform.strip().lower()
    row.handle = body.handle
    row.display_name = body.display_name
    row.style = body.style
    row.audience_geo = body.audience_geo
    row.audience_notes = body.audience_notes
    row.preferred_clip_length = body.preferred_clip_length
    row.preferred_hooks = body.preferred_hooks
    row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return _serialize_account(row)


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = db.query(Campaign).order_by(Campaign.score.desc(), Campaign.created_at.desc()).all()
    # SQLite/Postgres: null scores sort last-ish via Python if needed
    rows.sort(key=lambda c: (c.score is None, -(c.score or 0)))
    return rows


@router.post("/campaigns", response_model=CampaignOut)
def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    parsed = parse_campaign_brief(body.raw_brief)
    accounts = (
        db.query(SocialAccount)
        .filter(SocialAccount.platform.in_(list(POSTING_PLATFORMS)))
        .all()
    )
    geos = merge_audience_geos(accounts)

    budget_remaining = None
    if parsed.total_budget is not None:
        budget_remaining = parsed.total_budget - (parsed.budget_utilised or 0)

    result = score_campaign(
        cpm=parsed.cpm,
        total_budget=parsed.total_budget,
        budget_utilised=parsed.budget_utilised,
        audience_match=body.audience_match_score,
        footage_quality=body.footage_quality_score,
        requirement_simplicity=body.requirement_simplicity_score,
        viral_potential=body.viral_potential_score,
        competition=body.competition_score,
        approval_probability=body.approval_probability,
        expected_views=body.expected_views,
        estimated_production_cost=body.estimated_production_cost,
        account_geos=geos,
        required_geo=parsed.required_geo,
        has_rights=parsed.has_rights,
        eligibility_ok=True,
        unclear_instructions=parsed.unclear_instructions,
        requires_fake_engagement=parsed.requires_fake_engagement,
        misleading_content=parsed.misleading_content,
    )

    campaign = Campaign(
        name=parsed.name,
        brand=parsed.brand,
        external_url=body.external_url,
        raw_brief=body.raw_brief,
        status="rejected" if not result.is_recommended else "scored",
        cpm=parsed.cpm,
        total_budget=parsed.total_budget,
        budget_utilised=parsed.budget_utilised or 0,
        budget_remaining=budget_remaining,
        eligibility=parsed.eligibility,
        required_geo=parsed.required_geo,
        has_rights=parsed.has_rights,
        footage_quality_score=body.footage_quality_score,
        requirement_simplicity_score=body.requirement_simplicity_score,
        viral_potential_score=body.viral_potential_score,
        audience_match_score=body.audience_match_score,
        competition_score=body.competition_score,
        approval_probability=body.approval_probability,
        expected_views=body.expected_views,
        estimated_production_cost=body.estimated_production_cost,
        score=result.score,
        expected_profit=result.expected_profit,
        reject_reasons=result.reject_reasons,
        is_recommended=result.is_recommended,
    )
    db.add(campaign)
    db.flush()
    db.add(
        CampaignRequirement(
            campaign_id=campaign.id,
            required_hashtags=parsed.required_hashtags,
            required_tags=parsed.required_tags,
            required_disclosure=parsed.required_disclosure,
            min_duration_sec=parsed.min_duration_sec,
            max_duration_sec=parsed.max_duration_sec,
            requires_logo=parsed.requires_logo,
            requires_cta=parsed.requires_cta,
            cta_text=parsed.cta_text,
            is_immutable_snapshot=False,
        )
    )
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/campaigns/{campaign_id}/join", response_model=CampaignOut)
def mark_joined(campaign_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    from datetime import datetime, timezone

    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not campaign.is_recommended:
        raise HTTPException(400, "Campaign was not recommended — join only after reviewing reject reasons")
    campaign.status = "joined"
    campaign.joined_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    return campaign
