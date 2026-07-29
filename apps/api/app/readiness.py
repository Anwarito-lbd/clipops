"""Go-live readiness score toward 99% Operator Mode."""

from __future__ import annotations

from typing import Any

from app.security_audit import audit_settings, media_stack_status


def compute_go_live(
    *,
    settings: Any,
    db: Any,
    Campaign: Any,
    ClipVersion: Any,
    Render: Any,
    Post: Any,
    Submission: Any,
    ClipPerformance: Any,
    DiscoveredCampaign: Any,
    SocialAccount: Any,
) -> dict[str, Any]:
    media = media_stack_status(settings)
    security = audit_settings(settings)

    accounts = db.query(SocialAccount).filter(SocialAccount.platform == "tiktok").count()
    youtube_accounts = db.query(SocialAccount).filter(SocialAccount.platform == "youtube").count()
    discovered = db.query(DiscoveredCampaign).count()
    campaigns = db.query(Campaign).count()
    versions = db.query(ClipVersion).count()
    drafts = (
        db.query(Render)
        .filter(Render.status.in_(["DRAFT", "EXPORTED", "REVIEW_REQUIRED"]))
        .count()
    )
    exported = db.query(ClipVersion).filter(ClipVersion.status == "EXPORTED").count()
    posted = db.query(Post).count()
    submitted = db.query(Submission).count()
    perfs_with_views = (
        db.query(ClipPerformance)
        .filter((ClipPerformance.views > 0) | (ClipPerformance.verified_views > 0))
        .count()
    )

    items = [
        {
            "id": "cuda_asr",
            "label": "GPU ASR (CUDA + WhisperX/faster-whisper)",
            "done": bool(media.get("cuda") and (media.get("whisperx") or media.get("faster_whisper"))),
            "weight": 12,
            "how": "Already installed via scripts/install_whisperx_cuda.py",
        },
        {
            "id": "ffmpeg_remotion",
            "label": "FFmpeg + Remotion render service",
            "done": bool(media.get("ffmpeg") and media.get("remotion")),
            "weight": 10,
            "how": ".\\scripts\\start_remotion.ps1  (or start_stack.ps1)",
        },
        {
            "id": "secrets",
            "label": "Rotated secrets (bcrypt hash + strong JWT)",
            "done": bool(security.using_password_hash and security.jwt_ok),
            "weight": 10,
            "how": "python scripts/rotate_secrets.py --print-password",
        },
        {
            "id": "accounts",
            "label": "3 TikTok + 3 YouTube accounts configured",
            "done": accounts >= 3 and youtube_accounts >= 3,
            "weight": 8,
            "how": "Seeded on API start (6 posting accounts), or PATCH via /api/accounts",
        },
        {
            "id": "discover",
            "label": "At least one CR campaign discovered/scanned",
            "done": discovered >= 1 or campaigns >= 1,
            "weight": 10,
            "how": "Extension Scan OR POST /api/operator/discover/scrapling (public board)",
        },
        {
            "id": "joined_campaign",
            "label": "Campaign joined + footage processed",
            "done": versions >= 1,
            "weight": 12,
            "how": "Approve campaign → YOU Join on CR (bot notifies) → Upload Assets",
        },
        {
            "id": "draft_preview",
            "label": "Draft render exists for preview",
            "done": drafts >= 1,
            "weight": 10,
            "how": "Automatic after upload (wait for Assets status GENERATED)",
        },
        {
            "id": "exported",
            "label": "At least one clip approved/exported",
            "done": exported >= 1,
            "weight": 10,
            "how": "Review → Approve (promotes draft to EXPORTED)",
        },
        {
            "id": "posted",
            "label": "At least one post URL marked posted",
            "done": posted >= 1,
            "weight": 8,
            "how": "Exports → you Post on TikTok/YouTube → paste URL → Mark posted",
        },
        {
            "id": "submitted",
            "label": "At least one CR submission marked",
            "done": submitted >= 1,
            "weight": 5,
            "how": "Extension Highlight Submit → you click → Mark submitted in Tracking",
        },
        {
            "id": "metrics",
            "label": "Views logged (closes learning loop)",
            "done": perfs_with_views >= 1,
            "weight": 5,
            "how": "Tracking → update views after ~24–72h",
        },
    ]

    # Optional polish toward 99 (not required for month-1 start)
    optional = [
        {
            "id": "diarization",
            "label": "Speaker diarization (HF_TOKEN)",
            "done": bool(media.get("diarization_ready")),
            "weight": 0,
            "how": "Set HF_TOKEN in .env after accepting pyannote model terms",
        },
        {
            "id": "async_workers",
            "label": "Async Celery workers (optional)",
            "done": bool(media.get("redis") and not media.get("celery_eager")),
            "weight": 0,
            "how": "CELERY_EAGER=false + scripts/start_celery_worker.ps1",
        },
    ]

    earned = sum(i["weight"] for i in items if i["done"])
    total = sum(i["weight"] for i in items) or 1
    # Cap software+ops go-live at 99 — 100 reserved for sustained earning proof
    score = min(99, round(100 * earned / total))
    next_steps = [i for i in items if not i["done"]]
    return {
        "score": score,
        "target": 99,
        "earned_weight": earned,
        "total_weight": total,
        "media_readiness_pct": media.get("readiness_pct"),
        "items": items,
        "optional": optional,
        "next": [
            {"id": i["id"], "label": i["label"], "how": i["how"]} for i in next_steps[:3]
        ],
        "note": (
            "99% = software + one full human-gated dry run with real CR/TikTok/YouTube actions. "
            "Join and cash-out are NEVER automated — ClipOps only notifies you. "
            "£1K/month is a planning target, not included in this score."
        ),
    }
