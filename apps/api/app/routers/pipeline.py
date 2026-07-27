from __future__ import annotations

import hashlib
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from app.auth import require_operator
from app.config import get_settings
from app.db import (
    Campaign,
    ClipCandidate,
    ClipVersion,
    ComplianceCheck,
    ClipPerformance,
    Earning,
    Payout,
    Post,
    Render,
    SocialAccount,
    SourceAsset,
    Submission,
    DailyMetric,
    get_db,
)
from app.schemas import (
    ApproveRequest,
    AssetOut,
    ClipVersionOut,
    EarningsUpdate,
    MarkPostedRequest,
    MarkPayoutReceived,
    MarkSubmittedRequest,
    MetricsUpdate,
)
from app.storage_security import assert_allowed_upload, resolve_under_root, sanitize_filename
from app.jobs import enqueue_or_run, media_preview_url
from packages.shared_types.constants import ALLOWED_TRANSITIONS

router = APIRouter(tags=["pipeline"])


def _transition(current: str, new: str) -> None:
    if new in {"FAILED", "REJECTED"}:
        # REJECTED allowed from any non-terminal productive state
        if new == "REJECTED" and current not in {"FAILED"}:
            return
        if new == "FAILED":
            return
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise HTTPException(400, f"Illegal transition {current} → {new}")


@router.post("/campaigns/{campaign_id}/assets", response_model=AssetOut)
async def upload_asset(
    campaign_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    settings = get_settings()
    storage_root = Path(settings.storage_root)
    if not storage_root.is_absolute():
        storage_root = ROOT / storage_root

    # Stream with size cap — do not load unbounded into memory
    max_bytes = int(settings.max_upload_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            raise HTTPException(413, f"File exceeds max upload size ({settings.max_upload_mb} MB)")
        chunks.append(piece)
    data = b"".join(chunks)

    try:
        safe_name = assert_allowed_upload(file.filename or "upload.mp4", total, max_bytes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    content_type = (file.content_type or "").lower()
    if content_type and not (
        content_type.startswith("video/")
        or content_type in {"application/octet-stream", "application/mp4"}
    ):
        raise HTTPException(400, f"Unsupported content type: {content_type}")

    rel = Path("sources") / campaign_id / f"{uuid4()}_{safe_name}"
    dest = storage_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    asset = SourceAsset(
        campaign_id=campaign_id,
        filename=safe_name,
        storage_path=str(rel).replace("\\", "/"),
        content_hash=digest,
        status="IMPORTED",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    from app.tasks import process_asset

    enqueue_or_run(process_asset, asset.id)
    db.refresh(asset)
    return asset


@router.get("/media/{file_path:path}")
def serve_media(
    file_path: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Stream exported/source media for in-dashboard preview (auth required)."""
    settings = get_settings()
    storage_root = Path(settings.storage_root)
    if not storage_root.is_absolute():
        storage_root = ROOT / storage_root
    try:
        # Accept either storage-relative paths or absolute paths under storage_root
        raw = file_path.replace("\\", "/")
        if Path(raw).is_absolute():
            candidate = Path(raw).resolve()
            if not str(candidate).startswith(str(storage_root.resolve())):
                raise ValueError("Path escapes storage root")
            target = candidate
        else:
            target = resolve_under_root(storage_root, raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    if target.suffix.lower() not in {
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
        ".m4v",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".txt",
        ".json",
    }:
        raise HTTPException(400, "File type not previewable")
    return FileResponse(target, filename=sanitize_filename(target.name))


@router.get("/campaigns/{campaign_id}/assets", response_model=list[AssetOut])
def list_assets(campaign_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    return db.query(SourceAsset).filter(SourceAsset.campaign_id == campaign_id).all()


@router.post("/assets/{asset_id}/process", response_model=AssetOut)
def reprocess_asset(asset_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    asset = db.get(SourceAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    from app.tasks import process_asset

    enqueue_or_run(process_asset, asset.id)
    db.refresh(asset)
    return asset


@router.get("/campaigns/{campaign_id}/candidates")
def list_candidates(campaign_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    rows = (
        db.query(ClipCandidate)
        .filter(ClipCandidate.campaign_id == campaign_id)
        .order_by(ClipCandidate.rank)
        .all()
    )
    return [
        {
            "id": r.id,
            "start_sec": r.start_sec,
            "end_sec": r.end_sec,
            "transcript_excerpt": r.transcript_excerpt,
            "scores": r.scores,
            "total_score": r.total_score,
            "rank": r.rank,
            "selected": r.selected,
        }
        for r in rows
    ]


@router.get("/campaigns/{campaign_id}/versions", response_model=list[ClipVersionOut])
def list_versions(campaign_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    return (
        db.query(ClipVersion)
        .filter(ClipVersion.campaign_id == campaign_id)
        .order_by(ClipVersion.style, ClipVersion.created_at)
        .all()
    )


@router.get("/versions/{version_id}/compliance")
def get_compliance(version_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    row = (
        db.query(ComplianceCheck)
        .filter(ComplianceCheck.clip_version_id == version_id)
        .order_by(ComplianceCheck.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(404, "No compliance check")
    return {"id": row.id, "passed": row.passed, "checks": row.checks, "override_reason": row.override_reason}


@router.post("/versions/{version_id}/approve", response_model=ClipVersionOut)
def approve_version(
    version_id: str,
    body: ApproveRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    version = db.get(ClipVersion, version_id)
    if not version:
        raise HTTPException(404, "Version not found")
    check = (
        db.query(ComplianceCheck)
        .filter(ComplianceCheck.clip_version_id == version_id)
        .order_by(ComplianceCheck.created_at.desc())
        .first()
    )
    if check and not check.passed and not body.override_reason:
        raise HTTPException(400, "Compliance failed — provide override_reason to approve anyway")
    if check and not check.passed and body.override_reason:
        check.override_reason = body.override_reason
    _transition(version.status, "APPROVED")
    version.status = "APPROVED"
    db.commit()

    # Prefer promoting an existing draft render; otherwise render now
    render = (
        db.query(Render)
        .filter(Render.clip_version_id == version_id)
        .order_by(Render.created_at.desc())
        .first()
    )
    has_video = bool(
        render
        and render.video_path
        and Path(render.video_path).exists()
        and Path(render.video_path).stat().st_size > 0
    )
    if has_video:
        render.status = "EXPORTED"
        _transition("APPROVED", "EXPORTED")
        version.status = "EXPORTED"
        db.commit()
    else:
        from app.tasks import render_version

        enqueue_or_run(render_version, version.id, draft=False)
    db.refresh(version)
    return version


@router.post("/versions/{version_id}/reject", response_model=ClipVersionOut)
def reject_version(version_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    version = db.get(ClipVersion, version_id)
    if not version:
        raise HTTPException(404, "Version not found")
    _transition(version.status, "REJECTED")
    version.status = "REJECTED"
    db.commit()
    db.refresh(version)
    return version


@router.get("/versions/{version_id}/renders")
def list_renders(version_id: str, db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    settings = get_settings()
    rows = db.query(Render).filter(Render.clip_version_id == version_id).all()
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "account_slot": r.account_slot,
                "video_path": r.video_path,
                "caption_path": r.caption_path,
                "cover_path": r.cover_path,
                "checklist_path": r.checklist_path,
                "package_dir": r.package_dir,
                "status": r.status,
                "preview_url": media_preview_url(settings.storage_root, r.video_path, ROOT),
                "download_url": media_preview_url(settings.storage_root, r.video_path, ROOT),
            }
        )
    return out


@router.post("/versions/{version_id}/mark-posted")
def mark_posted(
    version_id: str,
    body: MarkPostedRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    version = db.get(ClipVersion, version_id)
    if not version:
        raise HTTPException(404, "Version not found")
    _transition(version.status, "MANUALLY_POSTED")
    post = Post(
        clip_version_id=version.id,
        social_account_id=version.social_account_id,
        tiktok_url=body.tiktok_url,
        posted_at=datetime.now(timezone.utc),
        status="MANUALLY_POSTED",
        notes=body.notes,
    )
    version.status = "MANUALLY_POSTED"
    db.add(post)
    db.flush()
    # Learning record — fill metrics later
    db.add(
        ClipPerformance(
            campaign_id=version.campaign_id,
            account_id=version.social_account_id,
            clip_version_id=version.id,
            post_id=post.id,
            hook_type=(version.context_intro or "generic")[:64],
            clip_length_band=version.duration_band,
            topic=None,
            editing_style=version.style,
            caption_style=version.subtitle_style,
            posting_time=post.posted_at,
            approval_status="posted",
        )
    )
    db.commit()
    db.refresh(post)
    return {"post_id": post.id, "status": post.status, "tiktok_url": post.tiktok_url}


@router.post("/posts/{post_id}/mark-submitted")
def mark_submitted(
    post_id: str,
    body: MarkSubmittedRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    version = db.get(ClipVersion, post.clip_version_id)
    if version:
        _transition(version.status, "SUBMITTED")
        version.status = "SUBMITTED"
        db.flush()
        _transition(version.status, "UNDER_REVIEW")
        version.status = "UNDER_REVIEW"
    sub = Submission(
        post_id=post.id,
        campaign_id=version.campaign_id if version else None,
        content_rewards_url=body.content_rewards_url,
        submitted_at=datetime.now(timezone.utc),
        review_started_at=datetime.now(timezone.utc),
        status="UNDER_REVIEW",
    )
    post.status = "SUBMITTED"
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"submission_id": sub.id, "status": sub.status}


@router.post("/posts/{post_id}/metrics")
def update_metrics(
    post_id: str,
    body: MetricsUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    d = date.fromisoformat(body.metric_date) if body.metric_date else date.today()
    row = (
        db.query(DailyMetric)
        .filter(DailyMetric.post_id == post_id, DailyMetric.metric_date == d)
        .first()
    )
    if not row:
        row = DailyMetric(post_id=post_id, metric_date=d)
        db.add(row)
    row.views = body.views
    row.likes = body.likes
    row.comments = body.comments
    row.shares = body.shares
    perf = db.query(ClipPerformance).filter(ClipPerformance.post_id == post_id).first()
    if perf:
        perf.views = body.views
        perf.likes = body.likes
        perf.comments = body.comments
        perf.shares = body.shares
    db.commit()
    return {"ok": True, "views": row.views}


@router.post("/submissions/{submission_id}/earnings")
def update_earnings(
    submission_id: str,
    body: EarningsUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    settings = get_settings()
    sub = db.get(Submission, submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    fee = body.provisional_amount * (1 - settings.platform_fee_multiplier)
    net = body.provisional_amount * settings.platform_fee_multiplier
    earning = (
        db.query(Earning).filter(Earning.submission_id == submission_id).first()
    )
    if not earning:
        earning = Earning(submission_id=submission_id)
        db.add(earning)
    earning.provisional_amount = body.provisional_amount
    earning.fee_amount = fee
    earning.net_amount = net
    earning.status = "EARNING"
    sub.status = "EARNING"
    # Sync learning earnings if linked via post
    post = db.get(Post, sub.post_id)
    if post:
        perf = db.query(ClipPerformance).filter(ClipPerformance.post_id == post.id).first()
        if perf:
            perf.earnings = float(net)
            perf.verified_views = perf.verified_views or perf.views
            perf.approval_status = "earning"
    db.flush()
    payout = None
    if body.mark_payout_ready:
        earning.status = "PAYOUT_READY"
        sub.status = "PAYOUT_READY"
        payout = Payout(
            earnings_id=earning.id,
            amount=net,
            ready_at=datetime.now(timezone.utc),
            status="PAYOUT_READY",
        )
        db.add(payout)
    db.commit()
    return {
        "earnings_id": earning.id,
        "net_amount": float(net),
        "fee_amount": float(fee),
        "payout_id": payout.id if payout else None,
        "status": earning.status,
        "alert": "PAYOUT_READY" if body.mark_payout_ready else None,
    }


@router.post("/payouts/{payout_id}/mark-received")
def mark_payout_received(
    payout_id: str,
    body: MarkPayoutReceived,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    payout = db.get(Payout, payout_id)
    if not payout:
        raise HTTPException(404, "Payout not found")
    payout.status = "PAID"
    payout.paid_at = datetime.now(timezone.utc)
    payout.notes = body.notes
    earning = db.get(Earning, payout.earnings_id)
    if earning:
        earning.status = "PAID"
    db.commit()
    return {"status": "PAID"}


@router.get("/tracking")
def tracking_board(db: Session = Depends(get_db), _user: str = Depends(require_operator)):
    posts = db.query(Post).order_by(Post.created_at.desc()).limit(100).all()
    out = []
    for p in posts:
        sub = db.query(Submission).filter(Submission.post_id == p.id).order_by(Submission.created_at.desc()).first()
        earning = None
        payout = None
        if sub:
            earning = db.query(Earning).filter(Earning.submission_id == sub.id).first()
            if earning:
                payout = db.query(Payout).filter(Payout.earnings_id == earning.id).first()
        out.append(
            {
                "post_id": p.id,
                "tiktok_url": p.tiktok_url,
                "post_status": p.status,
                "submission_id": sub.id if sub else None,
                "submission_status": sub.status if sub else None,
                "earnings_id": earning.id if earning else None,
                "provisional_amount": float(earning.provisional_amount) if earning else None,
                "net_amount": float(earning.net_amount) if earning and earning.net_amount is not None else None,
                "payout_id": payout.id if payout else None,
                "payout_status": payout.status if payout else None,
                "payout_ready": bool(payout and payout.status == "PAYOUT_READY"),
            }
        )
    return out


@router.post("/versions/{version_id}/regenerate")
def regenerate_version(
    version_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    """Re-run caption generation for a version (still needs human approve)."""
    version = db.get(ClipVersion, version_id)
    if not version:
        raise HTTPException(404, "Version not found")
    campaign = db.get(Campaign, version.campaign_id)
    account = db.get(SocialAccount, version.social_account_id)
    from workers.caption_generation.generate import generate_account_copy
    from app.db import CampaignRequirement

    req = None
    if version.requirements_snapshot_id:
        req = db.get(CampaignRequirement, version.requirements_snapshot_id)
    copy = generate_account_copy(
        style=version.style,
        campaign_name=campaign.name if campaign else "campaign",
        excerpt=version.hook_text or "",
        hashtags=list(req.required_hashtags) if req else [],
        tags=list(req.required_tags) if req else [],
        disclosure=req.required_disclosure if req else None,
        hook_variant=(version.hook_variant % 3) + 1,
    )
    version.hook_variant = (version.hook_variant % 3) + 1
    version.caption = copy["caption"]
    version.hook_text = copy["hook"]
    version.context_intro = copy.get("context_intro")
    _transition(version.status if version.status != "FAILED" else "REVIEW_REQUIRED", "REVIEW_REQUIRED")
    version.status = "REVIEW_REQUIRED"
    version.subtitle_style = "minimal" if version.subtitle_style == "bold" else "bold"
    db.commit()
    from app.tasks import render_version

    enqueue_or_run(render_version, version.id, draft=True)
    db.refresh(version)
    return {
        "id": version.id,
        "caption": version.caption,
        "hook_text": version.hook_text,
        "status": version.status,
        "account": account.display_name if account else None,
    }


@router.get("/versions/{version_id}/approval-card")
def approval_card(
    version_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    version = db.get(ClipVersion, version_id)
    if not version:
        raise HTTPException(404, "Not found")
    campaign = db.get(Campaign, version.campaign_id)
    account = db.get(SocialAccount, version.social_account_id)
    render = (
        db.query(Render)
        .filter(Render.clip_version_id == version_id)
        .order_by(Render.created_at.desc())
        .first()
    )
    check = (
        db.query(ComplianceCheck)
        .filter(ComplianceCheck.clip_version_id == version_id)
        .order_by(ComplianceCheck.created_at.desc())
        .first()
    )
    cand = db.get(ClipCandidate, version.candidate_id) if version.candidate_id else None
    settings = get_settings()
    score = float(cand.total_score) if cand else None
    pred = "HIGH" if score and score >= 80 else ("MEDIUM" if score and score >= 60 else "LOW")
    preview_url = None
    if render and render.video_path:
        vp = Path(render.video_path)
        storage_root = Path(settings.storage_root)
        if not storage_root.is_absolute():
            storage_root = ROOT / storage_root
        try:
            rel = vp.resolve().relative_to(storage_root.resolve())
            preview_url = f"/api/media/{rel.as_posix()}"
        except Exception:
            # Fall back to basename path under exports if already relative
            preview_url = f"/api/media/{str(render.video_path).replace(chr(92), '/')}"
    return {
        "id": version.id,
        "campaign": campaign.name if campaign else None,
        "account": account.display_name if account else None,
        "style": version.style,
        "caption": version.caption,
        "hook_text": version.hook_text,
        "duration_band": version.duration_band,
        "video_path": render.video_path if render else None,
        "preview_url": preview_url,
        "compliance_passed": check.passed if check else None,
        "compliance_checks": check.checks if check else [],
        "ai_score": score,
        "predicted_performance": pred,
        "expected_earnings": float(campaign.expected_profit)
        if campaign and campaign.expected_profit is not None
        else None,
        "open_campaign": campaign.external_url if campaign else None,
        "open_tiktok": settings.tiktok_url,
        "buttons": ["Approve", "Reject", "Regenerate", "Open Campaign", "Open TikTok"],
    }
