"""Affiliate marketing API — bios, pitches, schedule reminders (MoneyPrinterV2-safe subset)."""

from __future__ import annotations

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
    AffiliateProduct,
    AffiliateSchedule,
    OperatorNotification,
    SocialAccount,
    get_db,
)
from packages.affiliate import (
    apply_amazon_tag,
    build_bio,
    generate_pitch,
    next_cron_slots,
    should_notify_now,
)

router = APIRouter(tags=["affiliates"])


class AffiliateCreate(BaseModel):
    name: str
    product_url: str
    affiliate_tag: Optional[str] = None
    niche: Optional[str] = None
    talking_points: list[str] = Field(default_factory=list)
    disclosure: str = "Ad / affiliate link"
    is_active: bool = True


class BioRequest(BaseModel):
    social_account_id: Optional[str] = None
    platform: str = "twitter"
    display_name: Optional[str] = None
    niche: Optional[str] = None
    affiliate_product_id: Optional[str] = None
    extra_line: Optional[str] = None


class PitchRequest(BaseModel):
    product_id: str
    platform: str = "twitter"


class ScheduleCreate(BaseModel):
    product_id: str
    platform: str = "twitter"
    times_per_day: int = 2
    enabled: bool = True


def _serialize_product(p: AffiliateProduct) -> dict[str, Any]:
    settings = get_settings()
    tag = p.affiliate_tag or getattr(settings, "amazon_affiliate_tag", "") or ""
    url = apply_amazon_tag(p.product_url, tag) if tag else p.product_url
    return {
        "id": p.id,
        "name": p.name,
        "product_url": p.product_url,
        "affiliate_url": url,
        "affiliate_tag": tag or p.affiliate_tag,
        "niche": p.niche,
        "talking_points": p.talking_points or [],
        "disclosure": p.disclosure,
        "is_active": p.is_active,
    }


@router.get("/affiliates/status")
def affiliate_status(_user: str = Depends(require_operator)):
    settings = get_settings()
    return {
        "source": "MoneyPrinterV2 ideas (safe subset)",
        "repo": "https://github.com/FujiwaraChoki/MoneyPrinterV2",
        "amazon_tag_configured": bool(getattr(settings, "amazon_affiliate_tag", "")),
        "twitter_url": getattr(settings, "twitter_url", "https://x.com"),
        "implemented": [
            "Affiliate product store + Amazon tag on URLs",
            "Bio text with affiliate link for TikTok / YouTube / X",
            "Pitch drafts for operator to copy",
            "CRON-like schedule → JOIN/PROMOTE notifications (you post)",
        ],
        "not_implemented": [
            "Firefox browser Twitter bot",
            "Browser YouTube Shorts auto-upload",
            "Amazon marketplace scrape bot",
            "Local business scrape + cold email outreach",
        ],
        "note": "Paste bios into each account. ClipOps reminds you to promote — it does not auto-tweet.",
    }


@router.get("/affiliates/products")
def list_products(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = db.query(AffiliateProduct).order_by(AffiliateProduct.created_at.desc()).all()
    return [_serialize_product(p) for p in rows]


@router.post("/affiliates/products")
def create_product(
    body: AffiliateCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    settings = get_settings()
    tag = body.affiliate_tag or getattr(settings, "amazon_affiliate_tag", "") or None
    row = AffiliateProduct(
        name=body.name.strip(),
        product_url=body.product_url.strip(),
        affiliate_tag=tag,
        niche=body.niche,
        talking_points=body.talking_points,
        disclosure=body.disclosure,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_product(row)


@router.delete("/affiliates/products/{product_id}")
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    row = db.get(AffiliateProduct, product_id)
    if not row:
        raise HTTPException(404, "Product not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/affiliates/bio")
def make_bio(
    body: BioRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    account = None
    if body.social_account_id:
        account = db.get(SocialAccount, body.social_account_id)
    platform = (body.platform or (account.platform if account else "twitter")).lower()
    if platform == "x":
        platform = "twitter"
    display = body.display_name or (account.display_name if account else "Creator")
    niche = body.niche or (account.audience_notes if account else None) or "Daily clips & finds"
    affiliate_url = None
    if body.affiliate_product_id:
        prod = db.get(AffiliateProduct, body.affiliate_product_id)
        if not prod:
            raise HTTPException(404, "Affiliate product not found")
        settings = get_settings()
        tag = prod.affiliate_tag or getattr(settings, "amazon_affiliate_tag", "") or ""
        affiliate_url = apply_amazon_tag(prod.product_url, tag) if tag else prod.product_url
    bio = build_bio(
        display_name=display,
        niche=niche,
        affiliate_url=affiliate_url,
        platform=platform,
        extra_line=body.extra_line,
    )
    return {
        "platform": platform,
        "bio": bio,
        "affiliate_url": affiliate_url,
        "instructions": f"Copy into your {platform} profile bio. ClipOps does not edit profiles for you.",
    }


@router.post("/affiliates/pitch")
def make_pitch(
    body: PitchRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    prod = db.get(AffiliateProduct, body.product_id)
    if not prod:
        raise HTTPException(404, "Product not found")
    settings = get_settings()
    tag = prod.affiliate_tag or getattr(settings, "amazon_affiliate_tag", "") or ""
    url = apply_amazon_tag(prod.product_url, tag) if tag else prod.product_url
    platform = body.platform.lower()
    if platform == "x":
        platform = "twitter"
    pitch = generate_pitch(
        product_name=prod.name,
        product_url=url,
        talking_points=list(prod.talking_points or []),
        platform=platform,
        disclosure=prod.disclosure or "Ad / affiliate link",
    )
    open_url = {
        "twitter": getattr(settings, "twitter_url", "https://x.com"),
        "tiktok": settings.tiktok_url,
        "youtube": settings.youtube_url,
    }.get(platform, settings.tiktok_url)
    return {
        **pitch.to_dict(),
        "open_url": open_url,
        "manual_gate": "Copy pitch → open platform → you press Post. No browser bot.",
        "bot_can_post": False,
    }


@router.get("/affiliates/schedules")
def list_schedules(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = db.query(AffiliateSchedule).all()
    return [
        {
            "id": s.id,
            "product_id": s.product_id,
            "platform": s.platform,
            "times_per_day": s.times_per_day,
            "enabled": s.enabled,
            "suggested_utc_slots": next_cron_slots(times_per_day=s.times_per_day),
            "last_notified_at": s.last_notified_at.isoformat() if s.last_notified_at else None,
        }
        for s in rows
    ]


@router.post("/affiliates/schedules")
def create_schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    if not db.get(AffiliateProduct, body.product_id):
        raise HTTPException(404, "Product not found")
    row = AffiliateSchedule(
        product_id=body.product_id,
        platform=body.platform.lower(),
        times_per_day=body.times_per_day,
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "suggested_utc_slots": next_cron_slots(times_per_day=row.times_per_day),
        "note": "Scheduler creates PROMOTE NOW notifications — it does not post to X/TikTok/YouTube.",
    }


@router.post("/affiliates/schedules/run-due")
def run_due_schedules(
    force: bool = False,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Fire promote reminders for due schedules (cron hourly or operator button).

    Respects times_per_day cooldown via last_notified_at unless force=true
    (dashboard "Schedule + fire" uses force so the operator gets an immediate alert).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    fired = []
    skipped = []
    for sched in db.query(AffiliateSchedule).filter(AffiliateSchedule.enabled.is_(True)).all():
        prod = db.get(AffiliateProduct, sched.product_id)
        if not prod or not prod.is_active:
            continue
        if not should_notify_now(
            times_per_day=sched.times_per_day,
            last_notified_at=sched.last_notified_at,
            now=now,
            force=force,
        ):
            skipped.append({"product": prod.name, "reason": "cooldown"})
            continue
        tag = prod.affiliate_tag or getattr(settings, "amazon_affiliate_tag", "") or ""
        url = apply_amazon_tag(prod.product_url, tag) if tag else prod.product_url
        platform = sched.platform if sched.platform != "x" else "twitter"
        pitch = generate_pitch(
            product_name=prod.name,
            product_url=url,
            talking_points=list(prod.talking_points or []),
            platform=platform,
            disclosure=prod.disclosure or "Ad / affiliate link",
        )
        n = OperatorNotification(
            kind="promote_now",
            title=f"PROMOTE NOW ({platform}): {prod.name}",
            body=pitch.body[:500],
            action_url={
                "twitter": getattr(settings, "twitter_url", "https://x.com"),
                "tiktok": settings.tiktok_url,
                "youtube": settings.youtube_url,
            }.get(platform, settings.tiktok_url),
            action_label=f"Open {platform}",
            related_id=prod.id,
        )
        db.add(n)
        sched.last_notified_at = now
        fired.append({"product": prod.name, "platform": platform})
    db.commit()
    return {
        "fired": fired,
        "skipped": skipped,
        "count": len(fired),
        "bot_can_post": False,
        "note": "Notifications created. You copy the pitch and post yourself.",
    }
