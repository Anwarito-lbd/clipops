"""Operator Mode API — discovery inbox, top-3 approve, posting queue, notifications.

Safety: assists the operator's logged-in Content Rewards browser session via extension.
Never auto-posts to TikTok or auto-submits / auto-withdraws on Content Rewards.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from app.auth import require_operator
from app.config import get_settings
from app.db import (
    Campaign,
    CampaignRequirement,
    ClipVersion,
    ComplianceCheck,
    ClipPerformance,
    DiscoveredCampaign,
    Earning,
    OperatorNotification,
    OperatorSettings,
    Payout,
    Post,
    ProductionEvent,
    Render,
    SocialAccount,
    SourceAsset,
    Submission,
    get_db,
)
from packages.services.operations import EXHAUSTED_AT
from packages.campaign_engine.ranker import rank_discovered_campaigns
from packages.campaign_parser.parser import parse_campaign_brief
from packages.posting_queue.router import assert_versions_not_identical, build_posting_packages
from packages.analytics.tracker import summarise_earnings, summarise_performance, learning_hints
from packages.services.campaign_discovery import CampaignDiscoveryService
from packages.services.campaign_scoring import CampaignScoringService

router = APIRouter(tags=["operator"])


class DiscoveredItem(BaseModel):
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    name: str
    brand: Optional[str] = None
    cpm: Optional[float] = None
    total_budget: Optional[float] = None
    budget_utilised: Optional[float] = None
    budget_remaining_pct: Optional[float] = None
    required_geo: list[str] = Field(default_factory=list)
    required_hashtags: list[str] = Field(default_factory=list)
    required_tags: list[str] = Field(default_factory=list)
    required_disclosure: Optional[str] = None
    min_duration_sec: int = 15
    max_duration_sec: int = 60
    required_clips: int = 3
    requires_logo: bool = False
    requires_cta: bool = False
    forbidden_words: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    has_rights: bool = True
    unclear_instructions: bool = False
    requires_fake_engagement: bool = False
    misleading_content: bool = False
    brief_text: Optional[str] = None
    asset_urls: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class DiscoverBatch(BaseModel):
    campaigns: list[DiscoveredItem]
    source: str = "browser_extension"


def _normalise_campaign_numbers(item: dict[str, Any]) -> dict[str, Any]:
    """Re-derive money figures server-side from the raw brief text.

    The extension also parses these, but it is an untrusted client: a stale
    cached content script silently reported $0.70 CPM as $760 and produced a
    $4,947 EV on the worst-paying campaign. Whenever brief_text is available the
    server's parser wins, so one bad extension build cannot poison the ranking.
    Values are left null rather than guessed when nothing matches.
    """
    text = item.get("brief_text") or ""
    if not text.strip():
        return item

    from packages.campaign_parser.parser import (
        extract_approval_rate,
        extract_budget,
        extract_cpm,
        extract_max_payout,
        extract_payout_bounds,
        looks_like_multiple_campaigns,
    )

    # Titles carry the rate more reliably than body prose ("$5K Budget | $2 CPM").
    name = item.get("name") or ""
    combined = f"{name}\n{text}" if name else text

    if looks_like_multiple_campaigns(combined):
        # Several campaigns scraped into one card — no figure can be attributed.
        item["cpm"] = None
        item["total_budget"] = None
        item["budget_utilised"] = None
        item["budget_remaining_pct"] = None
        item["max_payout"] = None
        item["unclear_instructions"] = True
        return item

    server_cpm = extract_cpm(combined)
    if server_cpm is not None:
        item["cpm"] = server_cpm
    elif item.get("cpm") is not None:
        # Client claimed a rate the server cannot corroborate — drop it rather
        # than forecast earnings from an unverifiable number.
        item["cpm"] = None

    total, used = extract_budget(combined)
    if total is not None:
        item["total_budget"] = total
        if used is not None:
            item["budget_utilised"] = used
            item["budget_remaining_pct"] = round((1 - used / total) * 100, 1)

    max_payout = extract_max_payout(combined)
    if max_payout is None:
        # Whop's earnings panel states bounds as "$15 Min  $3000 Max".
        _low, high = extract_payout_bounds(combined)
        max_payout = high
    if max_payout is not None:
        item["max_payout"] = max_payout

    # The stated approval rate replaces the 70% assumption. A campaign approving
    # 3% of submissions earns ~23x less than the default would forecast.
    approval = extract_approval_rate(combined)
    if approval is not None:
        item["approval_probability"] = approval
    return item


def _brief_fetched_map(db: Session, items: list[dict[str, Any]]) -> None:
    """Carry each campaign's verified state into the ranking payload."""
    ids = [i.get("external_id") for i in items if i.get("external_id")]
    if not ids:
        return
    known = {
        r.external_id: bool(r.brief_fetched)
        for r in db.query(DiscoveredCampaign)
        .filter(DiscoveredCampaign.external_id.in_(ids))
        .all()
    }
    for i in items:
        i["brief_fetched"] = known.get(i.get("external_id"), False)


class BriefPayload(BaseModel):
    discovered_id: str
    brief_text: str
    asset_urls: list[str] = Field(default_factory=list)
    external_url: Optional[str] = None


class PayoutWatchPayload(BaseModel):
    amount: float
    currency: str = "USD"
    cashout_url: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


def _notify(
    db: Session,
    *,
    kind: str,
    title: str,
    body: str = "",
    action_url: str | None = None,
    action_label: str | None = None,
    related_id: str | None = None,
) -> OperatorNotification:
    n = OperatorNotification(
        kind=kind,
        title=title,
        body=body,
        action_url=action_url,
        action_label=action_label,
        related_id=related_id,
    )
    db.add(n)
    return n


@router.get("/operator/status")
def operator_status(_user: str = Depends(require_operator)):
    settings = get_settings()
    return {
        "mode": "operator",
        "automation_level": "85-90%",
        "manual_gates": [
            "Approve campaign",
            "Confirm TikTok post",
            "Confirm Content Rewards submission",
            "Confirm cash-out",
        ],
        "forbidden": [
            "Unattended Playwright Content Rewards bot",
            "Automatic TikTok posting",
            "Automatic CR submission",
            "Automatic payout withdrawal",
        ],
        "content_rewards_url": settings.content_rewards_url,
        "tiktok_url": settings.tiktok_url,
        "extension_required": True,
        "note": "Extension reads your already-logged-in CR session. You click Join / Post / Submit / Withdraw.",
    }


@router.get("/operator/readiness")
def operator_readiness(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """Scored checklist toward 99% go-live (software + first real dry run)."""
    from app.readiness import compute_go_live
    from app.db import (
        Campaign,
        ClipPerformance,
        ClipVersion,
        DiscoveredCampaign,
        Post,
        Render,
        SocialAccount,
        Submission,
    )

    return compute_go_live(
        settings=get_settings(),
        db=db,
        Campaign=Campaign,
        ClipVersion=ClipVersion,
        Render=Render,
        Post=Post,
        Submission=Submission,
        ClipPerformance=ClipPerformance,
        DiscoveredCampaign=DiscoveredCampaign,
        SocialAccount=SocialAccount,
    )


@router.post("/operator/discover")
def ingest_discovered(
    body: DiscoverBatch,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Ingest campaigns scanned from the operator's logged-in CR tab."""
    accounts = db.query(SocialAccount).filter(SocialAccount.platform == "tiktok").all()
    geos: list[str] = []
    for a in accounts:
        geos.extend(a.audience_geo or [])
    geos = list(dict.fromkeys(geos)) or ["US", "CA"]

    from packages.services.forecast import PerformanceLearningService

    perf_rows = []
    for p in db.query(ClipPerformance).all():
        perf_rows.append(
            {
                "views": p.views,
                "verified_views": p.verified_views,
                "approval_status": p.approval_status,
                "editing_style": p.editing_style,
            }
        )
    priors = PerformanceLearningService().historical_priors(perf_rows)

    payload = [_normalise_campaign_numbers(c.model_dump()) for c in body.campaigns]
    _brief_fetched_map(db, payload)
    all_ranked = rank_discovered_campaigns(
        payload,
        account_geos=geos,
        top_n=len(payload),
        historical_approval_rate=priors.get("historical_approval_rate"),
        historical_avg_views=priors.get("historical_avg_views"),
    )
    by_key = {(r.external_id or "", r.name): r for r in all_ranked}

    saved: list[dict[str, Any]] = []
    for item in body.campaigns:
        ranked = by_key.get((item.external_id or "", item.name))
        if ranked is None and all_ranked:
            ranked = next((r for r in all_ranked if r.name == item.name), all_ranked[0])
        if ranked is None:
            continue

        existing = None
        if item.external_id:
            existing = (
                db.query(DiscoveredCampaign)
                .filter(DiscoveredCampaign.external_id == item.external_id)
                .first()
            )
        protected = {"approved", "collecting", "producing", "ready", "posted", "submitted", "done"}
        if existing and existing.operator_status in protected:
            saved.append(
                {
                    "id": existing.id,
                    "name": existing.name,
                    "opportunity_score": existing.opportunity_score,
                    "operator_status": existing.operator_status,
                    "is_eligible": existing.is_eligible,
                }
            )
            continue

        row = existing or DiscoveredCampaign(external_id=item.external_id, name=item.name)
        row.external_url = item.external_url
        row.name = ranked.name
        row.brand = ranked.brand
        row.raw_payload = item.model_dump()
        row.cpm = ranked.cpm
        row.budget_remaining_pct = ranked.budget_remaining_pct
        row.difficulty = ranked.difficulty
        row.required_clips = ranked.required_clips
        row.min_duration_sec = ranked.min_duration_sec
        row.max_duration_sec = ranked.max_duration_sec
        row.opportunity_score = ranked.opportunity_score
        row.expected_profit = ranked.expected_profit
        row.is_eligible = ranked.is_eligible
        row.reject_reasons = ranked.reject_reasons
        row.brief_text = item.brief_text
        row.asset_urls = item.asset_urls
        row.operator_status = "discovered" if ranked.is_eligible else "rejected"
        if not existing:
            db.add(row)
        db.flush()
        saved.append(
            {
                "id": row.id,
                "name": row.name,
                "opportunity_score": row.opportunity_score,
                "operator_status": row.operator_status,
                "is_eligible": row.is_eligible,
            }
        )

    top_rows = (
        db.query(DiscoveredCampaign)
        .filter(DiscoveredCampaign.is_eligible.is_(True))
        .filter(DiscoveredCampaign.operator_status.in_(["discovered", "top3"]))
        .order_by(DiscoveredCampaign.opportunity_score.desc())
        .limit(3)
        .all()
    )
    for r in top_rows:
        r.operator_status = "top3"

    if top_rows:
        _notify(
            db,
            kind="campaigns_ready",
            title=f"{len(top_rows)} campaigns ranked for your approval",
            body="Review the best three and Approve Campaign to continue.",
            action_url="/operator",
            action_label="Open Operator Mode",
        )
    db.commit()
    return {
        "ingested": len(saved),
        "top3": [
            {"id": r.id, "name": r.name, "score": r.opportunity_score} for r in top_rows
        ],
    }


@router.get("/operator/top3")
def get_top3(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = (
        db.query(DiscoveredCampaign)
        .filter(DiscoveredCampaign.operator_status == "top3")
        .order_by(DiscoveredCampaign.opportunity_score.desc())
        .limit(3)
        .all()
    )
    # Fallback: best eligible discovered
    if not rows:
        rows = (
            db.query(DiscoveredCampaign)
            .filter(DiscoveredCampaign.is_eligible.is_(True))
            .filter(DiscoveredCampaign.operator_status.in_(["discovered", "top3"]))
            .order_by(DiscoveredCampaign.opportunity_score.desc())
            .limit(3)
            .all()
        )
    return [_serialize_discovered(r) for r in rows]


@router.get("/operator/discovered")
def list_discovered(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = db.query(DiscoveredCampaign).order_by(DiscoveredCampaign.opportunity_score.desc()).limit(100).all()
    return [_serialize_discovered(r) for r in rows]


def _serialize_discovered(r: DiscoveredCampaign) -> dict[str, Any]:
    return {
        "id": r.id,
        "external_id": r.external_id,
        "external_url": r.external_url,
        "name": r.name,
        "brand": r.brand,
        "cpm": float(r.cpm) if r.cpm is not None else None,
        "budget_remaining_pct": float(r.budget_remaining_pct) if r.budget_remaining_pct is not None else None,
        "difficulty": r.difficulty,
        "required_clips": r.required_clips,
        "min_duration_sec": r.min_duration_sec,
        "max_duration_sec": r.max_duration_sec,
        "opportunity_score": float(r.opportunity_score) if r.opportunity_score is not None else None,
        "expected_profit": float(r.expected_profit) if r.expected_profit is not None else None,
        "is_eligible": r.is_eligible,
        "reject_reasons": r.reject_reasons or [],
        "operator_status": r.operator_status,
        "campaign_id": r.campaign_id,
        "brief_text": r.brief_text,
        "asset_urls": r.asset_urls or [],
        "open_campaign_url": r.external_url,
        "actions": {
            "approve": True,
            "reject": True,
            "open_campaign": bool(r.external_url),
            "note": "After Approve, open the campaign in CR and click Join yourself — ClipOps does not auto-join.",
        },
    }


@router.post("/operator/discovered/{discovered_id}/approve")
def approve_discovered(
    discovered_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    row = db.get(DiscoveredCampaign, discovered_id)
    if not row:
        raise HTTPException(404, "Not found")
    if not row.is_eligible:
        raise HTTPException(400, "Campaign is not eligible — review reject reasons")

    brief = row.brief_text or row.name
    parsed = parse_campaign_brief(brief)
    # Prefer structured payload fields
    raw = row.raw_payload or {}
    campaign = Campaign(
        name=row.name,
        brand=row.brand or parsed.brand,
        external_url=row.external_url,
        raw_brief=brief,
        status="joined",
        cpm=row.cpm or parsed.cpm,
        score=row.opportunity_score,
        expected_profit=row.expected_profit,
        is_recommended=True,
        reject_reasons=[],
        required_geo=raw.get("required_geo") or parsed.required_geo,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(campaign)
    db.flush()
    db.add(
        CampaignRequirement(
            campaign_id=campaign.id,
            required_hashtags=raw.get("required_hashtags") or parsed.required_hashtags,
            required_tags=raw.get("required_tags") or parsed.required_tags,
            required_disclosure=raw.get("required_disclosure") or parsed.required_disclosure,
            min_duration_sec=row.min_duration_sec,
            max_duration_sec=row.max_duration_sec,
            requires_logo=bool(raw.get("requires_logo")),
            requires_cta=bool(raw.get("requires_cta")),
            forbidden_words=raw.get("forbidden_words") or [],
            forbidden_claims=raw.get("forbidden_claims") or [],
            # Approval works from the discover-page card, which carries none of
            # the real rules. Marked "card" so production refuses to run until
            # the campaign's own brief has been fetched.
            source="card",
            is_immutable_snapshot=False,
        )
    )
    row.campaign_id = campaign.id
    row.operator_status = "approved"
    _notify(
        db,
        kind="campaign_approved",
        title=f"Approved: {row.name}",
        body="Open the campaign in Content Rewards and click Join. Then collect brief/assets (extension assists).",
        action_url=row.external_url,
        action_label="Open campaign",
        related_id=row.id,
    )
    db.commit()
    return {
        "discovered_id": row.id,
        "campaign_id": campaign.id,
        "operator_status": row.operator_status,
        "next_steps": [
            "Open campaign in Content Rewards (your session)",
            "Click Join yourself — ClipOps does not auto-join",
            "Extension will extract brief + asset links after you open the page",
            "Upload/collect assets → ClipOps generates clips automatically",
        ],
        "open_campaign_url": row.external_url,
    }


@router.post("/operator/discovered/{discovered_id}/reject")
def reject_discovered(
    discovered_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    row = db.get(DiscoveredCampaign, discovered_id)
    if not row:
        raise HTTPException(404, "Not found")
    row.operator_status = "rejected"
    db.commit()
    return {"id": row.id, "operator_status": "rejected"}


@router.post("/operator/brief")
def save_brief(
    body: BriefPayload,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Brief extractor / asset collector from extension."""
    row = db.get(DiscoveredCampaign, body.discovered_id)
    if not row:
        raise HTTPException(404, "Not found")

    # Refuse the discover listing. It contains every campaign's text at once, so
    # saving it as one campaign's brief overwrites that campaign's real rules
    # with a blend of 170 others - worse than having no brief at all.
    text = body.brief_text or ""
    join_buttons = len(re.findall(r"join\s+campaign", text, re.I))
    if join_buttons > 1:
        raise HTTPException(
            400,
            f"That page lists {join_buttons} campaigns - it is the discover feed, "
            "not a campaign brief. Open the individual campaign page and retry.",
        )

    row.brief_text = body.brief_text
    row.asset_urls = body.asset_urls
    # Only a brief that actually yields rules counts as read. A capture that
    # parses to pure defaults leaves the campaign unverified.
    from packages.campaign_parser.parser import requirements_look_unread

    row.brief_fetched = not requirements_look_unread(
        parse_campaign_brief(text), text
    )
    if body.external_url:
        row.external_url = body.external_url
    if row.operator_status == "approved":
        row.operator_status = "collecting"

    # Mirror into linked campaign if present
    if row.campaign_id:
        camp = db.get(Campaign, row.campaign_id)
        if camp:
            camp.raw_brief = body.brief_text
            parsed = parse_campaign_brief(body.brief_text)
            req = (
                db.query(CampaignRequirement)
                .filter(
                    CampaignRequirement.campaign_id == camp.id,
                    CampaignRequirement.is_immutable_snapshot.is_(False),
                )
                .order_by(CampaignRequirement.created_at.desc())
                .first()
            )
            if req:
                req.required_hashtags = parsed.required_hashtags
                req.required_tags = parsed.required_tags
                req.required_disclosure = parsed.required_disclosure
                req.min_duration_sec = parsed.min_duration_sec
                req.max_duration_sec = parsed.max_duration_sec
                req.requires_logo = parsed.requires_logo
                req.requires_cta = parsed.requires_cta
                req.forbidden_words = parsed.forbidden_words
                req.forbidden_claims = parsed.forbidden_claims
                # A brief that yields only defaults means the detail page was
                # not actually captured - keep it marked unread so production
                # stays blocked rather than running on invented rules.
                from packages.campaign_parser.parser import requirements_look_unread

                req.source = (
                    "card"
                    if requirements_look_unread(parsed, body.brief_text)
                    else "brief"
                )
    _notify(
        db,
        kind="assets_ready",
        title=f"Brief/assets saved: {row.name}",
        body=f"{len(body.asset_urls)} asset URL(s). Download authorised assets, then upload into ClipOps Assets.",
        action_url="/assets",
        action_label="Open Assets",
        related_id=row.id,
    )
    db.commit()
    return {
        "ok": True,
        "discovered_id": row.id,
        "asset_urls": row.asset_urls,
        "campaign_id": row.campaign_id,
        "download_note": "Extension lists authorised download links; you confirm downloads. No unattended CR bot.",
    }


def _storage_root() -> Path:
    root = Path(get_settings().storage_root)
    return root if root.is_absolute() else (ROOT / root)


@router.get("/operator/today")
def operator_today(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """The daily driver: what to post, to which account, and what is overdue."""
    from packages.services.schedule import build_schedule, overdue_submissions

    accounts = [
        {"id": a.id, "label": a.display_name or a.handle}
        for a in db.query(SocialAccount)
        .filter(SocialAccount.platform == "tiktok", SocialAccount.is_active.is_(True))
        .order_by(SocialAccount.handle)
        .all()
    ]

    # Days since the first post decides whether the ramp still applies.
    first_post = db.query(Post).order_by(Post.posted_at.asc()).first()
    days_active = 0
    if first_post and first_post.posted_at:
        started = first_post.posted_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        days_active = (datetime.now(timezone.utc) - started).days

    posted_version_ids = {p.clip_version_id for p in db.query(Post).all()}
    ready = []
    for v in (
        db.query(ClipVersion)
        .filter(ClipVersion.status.in_(["APPROVED", "EXPORTED"]))
        .order_by(ClipVersion.created_at.asc())
        .all()
    ):
        if v.id in posted_version_ids:
            continue
        render = (
            db.query(Render)
            .filter(Render.clip_version_id == v.id, Render.content_hash.isnot(None))
            .order_by(Render.created_at.desc())
            .first()
        )
        if not render:
            continue  # nothing postable without a real rendered file
        camp = db.get(Campaign, v.campaign_id)
        ready.append(
            {
                "id": v.id,
                "account_id": v.social_account_id,
                "caption": v.caption,
                "hook_text": v.hook_text,
                "campaign_name": camp.name if camp else None,
                "preview_url": f"/api/media/{Path(render.video_path).name}"
                if render.video_path
                else None,
            }
        )

    schedule = build_schedule(
        ready_clips=ready, accounts=accounts, days_active=days_active
    )

    # Posted but not yet submitted - the backlog that costs money directly.
    submitted_post_ids = {s.post_id for s in db.query(Submission).all()}
    pending = [
        {
            "post_id": p.id,
            "clip_version_id": p.clip_version_id,
            "tiktok_url": p.tiktok_url,
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            "submitted": p.id in submitted_post_ids,
        }
        for p in db.query(Post).all()
    ]
    awaiting = overdue_submissions(pending)

    return {
        **schedule,
        "accounts": accounts,
        "ready_count": len(ready),
        "awaiting_submission": [a for a in awaiting if not a["submitted"]],
        "blocked": {
            "clips_awaiting_approval": db.query(ClipVersion)
            .filter(ClipVersion.status == "REVIEW_REQUIRED")
            .count(),
            "assets_failed": db.query(SourceAsset)
            .filter(SourceAsset.status == "FAILED")
            .count(),
        },
    }


@router.get("/operator/inbox")
def inbox_status(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """Footage waiting in the drop folder."""
    from packages.services.operations import human_bytes, scan_inbox

    root = _storage_root() / "inbox"
    root.mkdir(parents=True, exist_ok=True)
    names = {c.id: c.name for c in db.query(Campaign).all()}
    items = [i.to_dict() for i in scan_inbox(root, names)]
    ready = [i for i in items if not i["problem"]]
    return {
        "inbox_path": str(root),
        "items": items,
        "ready_count": len(ready),
        "total_size": human_bytes(sum(i["size_bytes"] for i in ready)),
        "how_to": "Drop video files into inbox/<campaign_id>/ then call import.",
        "campaign_folders": {cid: str(root / cid) for cid in names},
    }


@router.post("/operator/inbox/import")
def inbox_import(
    campaign_id: str | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Move dropped footage into its campaign and start processing."""
    from packages.services.operations import import_inbox_file, scan_inbox

    storage_root = _storage_root()
    root = storage_root / "inbox"
    root.mkdir(parents=True, exist_ok=True)
    names = {c.id: c.name for c in db.query(Campaign).all()}

    imported, skipped = [], []
    for item in scan_inbox(root, names):
        target = item.campaign_id or campaign_id
        if item.problem and not (campaign_id and "Loose file" in (item.problem or "")):
            skipped.append({"file": item.filename, "why": item.problem})
            continue
        if not target:
            skipped.append({"file": item.filename, "why": "No campaign to import into"})
            continue

        src = Path(item.path)
        dest, rel = import_inbox_file(src, storage_root, target)
        asset = SourceAsset(
            campaign_id=target,
            filename=dest.name,
            storage_path=rel,
            status="IMPORTED",
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

        from app.jobs import enqueue_or_run
        from app.tasks import process_asset

        enqueue_or_run(process_asset, asset.id)
        imported.append({"file": dest.name, "asset_id": asset.id, "campaign_id": target})

    return {"imported": imported, "skipped": skipped, "count": len(imported)}


@router.get("/operator/rotation")
def campaign_rotation(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """Which campaigns are running dry, so a replacement can be lined up early."""
    from packages.services.operations import rotation_signal

    out = []
    for camp in db.query(Campaign).filter(Campaign.status.notin_(["rejected"])).all():
        # Earnings attributable to this campaign, for the per-clipper cap.
        earned = sum(
            float(e.net_amount or e.provisional_amount or 0)
            for e in db.query(Earning)
            .join(Submission, Earning.submission_id == Submission.id)
            .join(Post, Submission.post_id == Post.id)
            .join(ClipVersion, Post.clip_version_id == ClipVersion.id)
            .filter(ClipVersion.campaign_id == camp.id)
            .all()
        )

        posted = (
            db.query(Post)
            .join(ClipVersion, Post.clip_version_id == ClipVersion.id)
            .filter(ClipVersion.campaign_id == camp.id)
            .count()
        )
        disc = (
            db.query(DiscoveredCampaign)
            .filter(DiscoveredCampaign.campaign_id == camp.id)
            .first()
        )
        raw = (disc.raw_payload if disc else None) or {}
        sig = rotation_signal(
            campaign_id=camp.id,
            campaign_name=camp.name,
            total_budget=float(camp.total_budget) if camp.total_budget else raw.get("total_budget"),
            budget_utilised=float(camp.budget_utilised) if camp.budget_utilised else raw.get("budget_utilised"),
            max_payout=raw.get("max_payout"),
            earned_so_far=earned,
            clips_posted=posted,
        )
        out.append(sig.to_dict())

    needs_action = [s for s in out if s["state"] != "healthy"]
    replacements = []
    if needs_action:
        replacements = [
            _serialize_discovered(r)
            for r in db.query(DiscoveredCampaign)
            .filter(
                DiscoveredCampaign.is_eligible.is_(True),
                DiscoveredCampaign.operator_status.in_(["discovered", "top3"]),
            )
            .order_by(DiscoveredCampaign.opportunity_score.desc())
            .limit(5)
            .all()
        ]
    return {
        "campaigns": out,
        "needs_action": needs_action,
        "suggested_replacements": replacements,
    }


@router.get("/operator/storage")
def storage_report(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """Source footage that can be deleted. Reports only - never deletes."""
    from packages.services.operations import find_reclaimable_sources, human_bytes

    storage_root = _storage_root()
    campaigns = []
    for camp in db.query(Campaign).all():
        assets = db.query(SourceAsset).filter(SourceAsset.campaign_id == camp.id).all()
        versions = db.query(ClipVersion).filter(ClipVersion.campaign_id == camp.id).all()
        disc = (
            db.query(DiscoveredCampaign)
            .filter(DiscoveredCampaign.campaign_id == camp.id)
            .first()
        )
        raw = (disc.raw_payload if disc else None) or {}
        total_budget = float(camp.total_budget) if camp.total_budget else raw.get("total_budget")
        used = float(camp.budget_utilised) if camp.budget_utilised else raw.get("budget_utilised")
        exhausted = bool(
            total_budget and used is not None and (used / total_budget) >= EXHAUSTED_AT
        )
        campaigns.append(
            {
                "id": camp.id,
                "name": camp.name,
                "exhausted": exhausted,
                "source_paths": [a.storage_path for a in assets],
                "version_statuses": [v.status for v in versions],
            }
        )

    candidates = find_reclaimable_sources(storage_root=storage_root, campaigns=campaigns)
    total = sum(c.bytes_freed for c in candidates)
    return {
        "reclaimable": [c.to_dict() for c in candidates],
        "total_bytes": total,
        "total_human": human_bytes(total),
        "policy": (
            "Only source footage from exhausted campaigns whose clips are all "
            "posted or resolved. Exports, captions and covers are never deleted - "
            "they are your evidence if a submission's views are disputed."
        ),
    }


@router.post("/operator/storage/reclaim")
def storage_reclaim(
    campaign_id: str,
    confirm: bool = False,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Delete one campaign's source footage. Requires confirm=true."""
    from packages.services.operations import human_bytes

    report = storage_report(db=db, _user=_user)
    match = next(
        (c for c in report["reclaimable"] if c["campaign_id"] == campaign_id), None
    )
    if match is None:
        raise HTTPException(
            400,
            "That campaign's footage is not reclaimable - it is still active, or "
            "some of its clips have not been posted yet.",
        )
    if not confirm:
        return {
            "dry_run": True,
            "would_delete": match["paths"],
            "would_free": human_bytes(match["bytes_freed"]),
            "note": "Re-send with confirm=true to delete. This cannot be undone.",
        }

    deleted, failed = [], []
    for p in match["paths"]:
        try:
            Path(p).unlink()
            deleted.append(p)
        except OSError as exc:
            failed.append({"path": p, "error": str(exc)})

    # Keep the rows: they record what was made from what, and re-import can refill.
    for a in db.query(SourceAsset).filter(SourceAsset.campaign_id == campaign_id).all():
        a.error_message = "Source file reclaimed to free disk space"
    db.commit()
    return {
        "deleted": deleted,
        "failed": failed,
        "freed": human_bytes(match["bytes_freed"]),
    }


@router.get("/operator/discovered/by-url")
def discovered_by_url(
    url: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Find a scanned campaign from the page URL currently open in a tab.

    Lets the extension attribute a brief to the right campaign when pulling
    several campaign tabs at once, without the operator selecting each one.
    """
    clean = (url or "").split("?")[0].rstrip("/")
    if not clean:
        raise HTTPException(400, "url is required")

    matches = (
        db.query(DiscoveredCampaign)
        .filter(DiscoveredCampaign.external_url.in_([clean, clean + "/"]))
        .limit(2)
        .all()
    )
    # The scan stores the listing URL for every card it finds there, so a URL
    # shared by several campaigns identifies none of them. Returning the first
    # would attribute one campaign's brief to another.
    if len(matches) > 1:
        raise HTTPException(
            409,
            "That URL is shared by multiple campaigns (it is the discover feed). "
            "Open the individual campaign page instead.",
        )
    row = matches[0] if matches else None
    if row is None:
        # Campaign pages usually end in a slug that also appears in the stored
        # URL; fall back to matching on that last path segment.
        slug = clean.rsplit("/", 1)[-1]
        if len(slug) >= 6:
            row = (
                db.query(DiscoveredCampaign)
                .filter(DiscoveredCampaign.external_url.like(f"%{slug}%"))
                .first()
            )
    if row is None:
        raise HTTPException(404, "No scanned campaign matches that URL")
    return {"id": row.id, "name": row.name, "operator_status": row.operator_status}


@router.get("/operator/queue")
def posting_queue(
    campaign_id: str | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    # Only clips actually cleared for posting. Without this filter REJECTED and
    # not-yet-approved versions appeared in the posting queue next to good ones.
    q = db.query(ClipVersion).filter(ClipVersion.status.in_(["APPROVED", "EXPORTED"]))
    if campaign_id:
        q = q.filter(ClipVersion.campaign_id == campaign_id)
    versions = q.order_by(ClipVersion.created_at.desc()).limit(200).all()
    # group by campaign, take latest 3 styles
    by_camp: dict[str, list] = {}
    for v in versions:
        by_camp.setdefault(v.campaign_id, []).append(v)

    settings = get_settings()
    out = []
    for cid, vs in by_camp.items():
        # Every approved clip surfaces. The old "one per style, max 3" dedup
        # silently discarded 2 of every 5 rendered clips, since more clips are
        # selected than there are accounts.
        picked = vs
        slot_by_version: dict[str, int] = {}
        for v in picked:
            latest = (
                db.query(Render)
                .filter(Render.clip_version_id == v.id)
                .order_by(Render.created_at.desc())
                .first()
            )
            if latest and latest.account_slot:
                slot_by_version[v.id] = latest.account_slot
        v_dicts = [
            {
                "id": v.id,
                "campaign_id": v.campaign_id,
                "style": v.style,
                "caption": v.caption,
                "status": v.status,
                # Authoritative slot from the render, so the queue label matches
                # the on-disk exports/<campaign>/account-N folder.
                "account_slot": slot_by_version.get(v.id),
            }
            for v in picked
        ]
        renders = []
        comp_map: dict[str, Any] = {}
        hashes: list[str | None] = []
        for v in picked:
            for r in db.query(Render).filter(Render.clip_version_id == v.id).all():
                renders.append(
                    {
                        "clip_version_id": v.id,
                        "video_path": r.video_path,
                        "package_dir": r.package_dir,
                        "content_hash": r.content_hash,
                        "account_slot": r.account_slot,
                    }
                )
                hashes.append(r.content_hash)
            c = (
                db.query(ComplianceCheck)
                .filter(ComplianceCheck.clip_version_id == v.id)
                .order_by(ComplianceCheck.created_at.desc())
                .first()
            )
            if c:
                comp_map[v.id] = {"checks": c.checks, "passed": c.passed}
        packages = build_posting_packages(v_dicts, renders, comp_map)
        dup_ok = assert_versions_not_identical(hashes)
        for p in packages:
            p.duplicate_safe = dup_ok
            d = p.to_dict()
            d["open_tiktok"] = settings.tiktok_url
            d["buttons"] = ["Download", "Copy Caption", "Open TikTok"]
            d["manual_gate"] = "You click TikTok's final Post button"
            out.append(d)
    return out


@router.get("/operator/submission-assist/{post_id}")
def submission_assist(
    post_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    version = db.get(ClipVersion, post.clip_version_id)
    discovered = None
    if version:
        discovered = (
            db.query(DiscoveredCampaign)
            .filter(DiscoveredCampaign.campaign_id == version.campaign_id)
            .first()
        )
    settings = get_settings()
    return {
        "post_id": post.id,
        "tiktok_url": post.tiktok_url,
        "campaign_url": discovered.external_url if discovered else None,
        "prefill": {
            "tiktok_url": post.tiktok_url,
            "caption": version.caption if version else None,
            "account_style": version.style if version else None,
        },
        "open_content_rewards": discovered.external_url or settings.content_rewards_url,
        "highlight": "Submit",
        "manual_gate": "ClipOps opens/prepares the page; you confirm the final Submit click.",
        "extension_hint": "submission-assistant highlights the Submit button — does not click it.",
    }


@router.post("/operator/payout-watch")
def payout_watch(
    body: PayoutWatchPayload,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Extension reports payout-ready amount from CR dashboard."""
    settings = get_settings()
    cashout = body.cashout_url or settings.content_rewards_url
    _notify(
        db,
        kind="payout_ready",
        title=f"{body.currency} {body.amount:.2f} is ready for withdrawal",
        body="ClipOps can open the cash-out page. You confirm the transfer (Whop after review).",
        action_url=cashout,
        action_label="Open Cash-out",
    )
    db.commit()
    return {
        "alert": True,
        "amount": body.amount,
        "currency": body.currency,
        "open_cashout_url": cashout,
        "manual_gate": "You personally confirm the withdrawal",
    }


@router.get("/operator/notifications")
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    q = db.query(OperatorNotification).order_by(OperatorNotification.created_at.desc())
    if unread_only:
        q = q.filter(OperatorNotification.read.is_(False))
    rows = q.limit(50).all()
    return [
        {
            "id": n.id,
            "kind": n.kind,
            "title": n.title,
            "body": n.body,
            "action_url": n.action_url,
            "action_label": n.action_label,
            "read": n.read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.post("/operator/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    n = db.get(OperatorNotification, notification_id)
    if not n:
        raise HTTPException(404, "Not found")
    n.read = True
    db.commit()
    return {"ok": True}


@router.get("/operator/analytics")
def operator_analytics(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    posts = db.query(Post).all()
    versions = {v.id: v for v in db.query(ClipVersion).all()}
    accounts = {a.id: a for a in db.query(SocialAccount).all()}
    perfs = {p.post_id: p for p in db.query(ClipPerformance).all() if p.post_id}
    perf_rows = []
    for p in posts:
        v = versions.get(p.clip_version_id)
        a = accounts.get(p.social_account_id)
        cp = perfs.get(p.id)
        perf_rows.append(
            {
                "views": int(cp.views) if cp else 0,
                "style": v.style if v else None,
                "account": a.handle if a else None,
            }
        )
    earnings = [
        {
            "provisional_amount": float(e.provisional_amount or 0),
            "net_amount": float(e.net_amount) if e.net_amount is not None else None,
            "status": e.status,
        }
        for e in db.query(Earning).all()
    ]
    performance = summarise_performance(perf_rows)
    money = summarise_earnings(earnings)
    payouts_ready = db.query(Payout).filter(Payout.status == "PAYOUT_READY").count()
    return {
        "performance": performance,
        "earnings": money,
        "payouts_ready": payouts_ready,
        "learning_hints": learning_hints(performance),
    }


@router.get("/operator/home")
def operator_home(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """£1K-style control home: target, earnings, forecast, campaigns, today queue."""
    from calendar import monthrange
    from packages.services.forecast import ForecastService

    settings_row = db.query(OperatorSettings).first()
    monthly_target = float(settings_row.monthly_target) if settings_row else 1000.0
    currency = (settings_row.currency if settings_row else None) or "GBP"
    earnings = db.query(Earning).all()
    current = sum(float(e.net_amount or e.provisional_amount or 0) for e in earnings)
    progress = round((current / monthly_target) * 100, 1) if monthly_target else 0

    perfs = db.query(ClipPerformance).all()
    verified = sum(int(p.verified_views or p.views or 0) for p in perfs)
    approved = sum(
        1
        for p in perfs
        if (p.approval_status or "").lower() in {"accepted", "earning", "paid", "approved"}
    )
    approval_rate = (approved / len(perfs)) if perfs else 0.70
    avg_views = (
        round(sum(int(p.views or 0) for p in perfs) / len(perfs), 0) if perfs else 8210
    )
    effective_cpm = round((current / verified) * 1000, 2) if verified else 0.0

    now = datetime.now(timezone.utc)
    days_in_month = monthrange(now.year, now.month)[1]
    forecast = ForecastService().forecast(
        monthly_target=monthly_target,
        currency=currency,
        current_earnings=current,
        days_elapsed=now.day,
        days_in_month=days_in_month,
        clips_produced=db.query(ClipVersion).count(),
        clips_posted=db.query(Post).count(),
        approval_rate=approval_rate if perfs else 0.70,
        avg_views_per_clip=float(avg_views),
        planning_cpm=2.0,
    )

    top3 = (
        db.query(DiscoveredCampaign)
        .filter(DiscoveredCampaign.operator_status == "top3")
        .order_by(DiscoveredCampaign.opportunity_score.desc())
        .limit(3)
        .all()
    )
    if not top3:
        top3 = (
            db.query(DiscoveredCampaign)
            .filter(DiscoveredCampaign.is_eligible.is_(True))
            .order_by(DiscoveredCampaign.opportunity_score.desc())
            .limit(3)
            .all()
        )

    accounts = (
        db.query(SocialAccount)
        .filter(SocialAccount.platform == "tiktok")
        .order_by(SocialAccount.handle)
        .all()
    )
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_accounts = []
    for a in accounts:
        posted_today = (
            db.query(Post)
            .filter(Post.social_account_id == a.id, Post.posted_at >= day_start)
            .count()
        )
        today_accounts.append(
            {
                "id": a.id,
                "label": a.display_name,
                "style": a.style,
                "preferred_clip_length": a.preferred_clip_length,
                "preferred_hooks": a.preferred_hooks or [],
                "done": posted_today,
                "target": 3,
                "complete": posted_today >= 3,
            }
        )

    waiting = (
        db.query(ClipVersion).filter(ClipVersion.status == "REVIEW_REQUIRED").count()
    )
    events = (
        db.query(ProductionEvent)
        .order_by(ProductionEvent.created_at.desc())
        .limit(20)
        .all()
    )
    payout_ready_amt = sum(
        float(p.amount or 0)
        for p in db.query(Payout).filter(Payout.status == "PAYOUT_READY").all()
    )

    return {
        "month_label": now.strftime("%B %Y").upper(),
        "currency": currency,
        "monthly_target": monthly_target,
        "current_earnings": round(current, 2),
        "progress_pct": progress,
        "verified_views": verified,
        "approval_rate": round(approval_rate * 100, 1),
        "avg_views_per_clip": avg_views,
        "effective_cpm": effective_cpm,
        "clips_produced": db.query(ClipVersion).count(),
        "clips_posted": db.query(Post).count(),
        "payout_ready": round(payout_ready_amt, 2),
        "forecast": forecast.to_dict(),
        "campaigns": [_serialize_discovered(r) for r in top3],
        "today_accounts": today_accounts,
        "clips_waiting_approval": waiting,
        "production_queue": [
            {
                "id": e.id,
                "title": e.title,
                "status": e.status,
                "at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in reversed(events)
        ],
    }


@router.get("/operator/production-queue")
def production_queue(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    events = (
        db.query(ProductionEvent)
        .order_by(ProductionEvent.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": e.id,
            "campaign_id": e.campaign_id,
            "title": e.title,
            "status": e.status,
            "at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/operator/learning")
def learning_board(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    from packages.services.forecast import PerformanceLearningService

    accounts = {a.id: a for a in db.query(SocialAccount).all()}
    rows = []
    for p in db.query(ClipPerformance).all():
        acc = accounts.get(p.account_id)
        rows.append(
            {
                "campaign_id": p.campaign_id,
                "account_id": p.account_id,
                "account_label": acc.display_name if acc else p.account_id,
                "hook_type": p.hook_type,
                "clip_length_band": p.clip_length_band,
                "editing_style": p.editing_style,
                "caption_style": p.caption_style,
                "views": p.views,
                "verified_views": p.verified_views,
                "likes": p.likes,
                "comments": p.comments,
                "shares": p.shares,
                "approval_status": p.approval_status,
                "earnings": float(p.earnings or 0),
            }
        )
    return PerformanceLearningService().analyse(rows)


@router.post("/operator/demo/seed-top3")
def demo_seed_top3(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """Seed sample discovered campaigns for Operator Mode demo without the extension."""
    sample = [
        DiscoveredItem(
            external_id="demo-voltpop",
            external_url="https://www.contentrewards.com",
            name="VoltPop Summer Push",
            brand="VoltPop",
            cpm=8.5,
            total_budget=25000,
            budget_utilised=10500,
            budget_remaining_pct=58,
            required_geo=["US", "CA"],
            required_hashtags=["#VoltPop", "#ContentRewards"],
            required_tags=["@voltpop"],
            required_disclosure="Paid partnership",
            min_duration_sec=20,
            max_duration_sec=45,
            required_clips=3,
            brief_text="VoltPop Summer Push\nCPM: $8.50\nBudget: $25000 utilised 42%\nGeo: US CA\nDuration: 20-45 seconds\n#VoltPop #ContentRewards @voltpop\nDisclosure: Paid partnership\nCTA: Link in bio",
            asset_urls=["https://example.com/asset1.mp4"],
        ),
        DiscoveredItem(
            external_id="demo-learnhub",
            external_url="https://www.contentrewards.com",
            name="LearnHub Story Explainer",
            brand="LearnHub",
            cpm=6.2,
            total_budget=40000,
            budget_utilised=8000,
            budget_remaining_pct=80,
            required_geo=["US"],
            required_hashtags=["#LearnHub"],
            required_disclosure="Paid partnership",
            min_duration_sec=25,
            max_duration_sec=60,
            required_clips=3,
            brief_text="LearnHub Story Explainer\nCPM $6.2\nBudget 40000 utilised 20%\nGeo US\n#LearnHub\nDisclosure: Paid partnership",
        ),
        DiscoveredItem(
            external_id="demo-reactco",
            external_url="https://www.contentrewards.com",
            name="ReactCo Commentary Drop",
            brand="ReactCo",
            cpm=5.0,
            total_budget=15000,
            budget_utilised=3000,
            budget_remaining_pct=80,
            required_geo=["US", "CA"],
            required_hashtags=["#ReactCo"],
            required_disclosure="Paid partnership",
            min_duration_sec=15,
            max_duration_sec=40,
            required_clips=3,
            brief_text="ReactCo Commentary Drop\nCPM 5\nBudget 15000 utilised 20%\n#ReactCo\nDisclosure: Paid partnership",
        ),
        DiscoveredItem(
            external_id="demo-bad",
            name="Exhausted Fake Engage",
            brand="BadBrand",
            cpm=12.0,
            total_budget=10000,
            budget_utilised=9500,
            budget_remaining_pct=5,
            required_geo=["JP"],
            requires_fake_engagement=True,
            brief_text="buy followers\nBudget utilised 95%\nGeo JP",
        ),
    ]
    return ingest_discovered(DiscoverBatch(campaigns=sample, source="demo"), db, _user)


@router.post("/operator/clear-demo")
def clear_demo_data(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    """Remove seeded demo campaigns so Operator Mode only shows real CR scans."""
    demo_ids = ("demo-voltpop", "demo-learnhub", "demo-reactco", "demo-bad")
    demo_names = {
        "VoltPop Summer Push",
        "LearnHub Story Explainer",
        "ReactCo Commentary Drop",
        "Exhausted Fake Engage",
    }
    rows = db.query(DiscoveredCampaign).all()
    removed = 0
    for r in rows:
        if (
            (r.external_id or "") in demo_ids
            or r.name in demo_names
            or (r.raw_payload or {}).get("source") == "demo"
            or str((r.raw_payload or {}).get("external_id") or "").startswith("demo-")
        ):
            db.delete(r)
            removed += 1
    camp_removed = 0
    for c in db.query(Campaign).all():
        if c.name not in demo_names:
            continue
        db.query(CampaignRequirement).filter(CampaignRequirement.campaign_id == c.id).delete()
        db.delete(c)
        camp_removed += 1
    db.commit()
    return {
        "removed_discovered": removed,
        "removed_campaigns": camp_removed,
        "next": "Open Content Rewards logged-in → ClipOps extension → Scan campaigns",
    }


class PasteBriefIn(BaseModel):
    """Manual fallback when DOM scan misses — paste a real CR brief."""

    name: Optional[str] = None
    brief_text: str
    external_url: Optional[str] = None
    external_id: Optional[str] = None


@router.post("/operator/paste-brief")
def paste_brief(
    body: PasteBriefIn,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Ingest one real campaign from pasted brief text (no demo)."""
    text = (body.brief_text or "").strip()
    if len(text) < 20:
        raise HTTPException(400, "Paste a fuller campaign brief (at least ~20 chars)")
    parsed = parse_campaign_brief(text)
    item = DiscoveredItem(
        external_id=body.external_id or f"paste-{hash(text) & 0xFFFFFFFF:x}",
        external_url=body.external_url or get_settings().content_rewards_url,
        name=body.name or parsed.name or text.splitlines()[0][:120],
        brand=parsed.brand,
        cpm=parsed.cpm,
        total_budget=parsed.total_budget,
        budget_utilised=parsed.budget_utilised,
        required_geo=parsed.required_geo,
        required_hashtags=parsed.required_hashtags,
        required_tags=parsed.required_tags,
        required_disclosure=parsed.required_disclosure,
        min_duration_sec=parsed.min_duration_sec or 15,
        max_duration_sec=parsed.max_duration_sec or 60,
        requires_logo=parsed.requires_logo,
        requires_cta=parsed.requires_cta,
        has_rights=parsed.has_rights,
        unclear_instructions=parsed.unclear_instructions,
        requires_fake_engagement=parsed.requires_fake_engagement,
        misleading_content=parsed.misleading_content,
        brief_text=text,
        raw={"source": "paste_brief"},
    )
    out = ingest_discovered(DiscoverBatch(campaigns=[item], source="paste_brief"), db, _user)
    return out
