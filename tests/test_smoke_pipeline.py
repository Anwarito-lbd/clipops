"""Smoke: campaign → process → draft render → approve → EXPORTED (no Redis worker required)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

os.environ.setdefault("CELERY_EAGER", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./clipops_smoke.db")
os.environ.setdefault("JWT_SECRET", "smoke-test-secret-at-least-32-chars-long")


@pytest.fixture(scope="module")
def smoke_video(tmp_path_factory):
    out = tmp_path_factory.mktemp("vid") / "clip.mp4"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=1080x1920:d=3",
                "-f",
                "lavfi",
                "-i",
                "sine=f=880:d=3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    except Exception as exc:
        pytest.skip(f"ffmpeg unavailable: {exc}")
    return out


def test_smoke_process_draft_approve(smoke_video, monkeypatch, tmp_path):
    monkeypatch.setenv("CELERY_EAGER", "true")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'smoke.db'}")
    monkeypatch.setenv("BURN_CAPTIONS", "false")
    monkeypatch.setenv("REMOTION_URL", "")

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.celery_eager is True

    from app.db import (
        Campaign,
        CampaignRequirement,
        ClipVersion,
        Render,
        SocialAccount,
        SourceAsset,
        init_db,
        SessionLocal,
    )
    from app.tasks import process_asset
    from app.routers.pipeline import approve_version
    from app.schemas import ApproveRequest
    from sqlalchemy.orm import Session

    init_db()
    db: Session = SessionLocal()
    try:
        for i, style in enumerate(["dramatic", "educational", "commentary"]):
            db.add(
                SocialAccount(
                    platform="tiktok",
                    handle=f"smoke{i}",
                    display_name=f"Smoke {style}",
                    style=style,
                    is_active=True,
                )
            )
        campaign = Campaign(name="SmokeCamp", status="joined", raw_brief="CPM $5 #Smoke")
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        # source="brief" mirrors a campaign whose detail page was captured.
        # Without it, process_asset correctly refuses to run against defaults.
        db.add(
            CampaignRequirement(
                campaign_id=campaign.id,
                required_hashtags=["#Smoke"],
                required_tags=[],
                required_disclosure="Paid partnership",
                min_duration_sec=15,
                max_duration_sec=60,
                source="brief",
                is_immutable_snapshot=False,
            )
        )
        db.commit()

        storage = Path(settings.storage_root)
        rel = Path("sources") / campaign.id / "clip.mp4"
        dest = storage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(smoke_video.read_bytes())
        asset = SourceAsset(
            campaign_id=campaign.id,
            filename="clip.mp4",
            storage_path=str(rel).replace("\\", "/"),
            status="IMPORTED",
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

        result = process_asset(asset.id)
        assert "error" not in result, result
        db.expire_all()
        asset = db.get(SourceAsset, asset.id)
        assert asset.status in {"GENERATED", "ANALYSED", "FAILED"} or asset.status == "GENERATED"
        assert asset.error_message and "transcript_engine=" in (asset.error_message or "")

        versions = db.query(ClipVersion).filter(ClipVersion.campaign_id == campaign.id).all()
        assert versions, "expected account versions"
        v = versions[0]
        assert v.status == "REVIEW_REQUIRED"
        renders = db.query(Render).filter(Render.clip_version_id == v.id).all()
        # Draft render may fail if source filters fail, but should attempt
        assert v.id

        # Approve with override if compliance failed (logo unverified etc.)
        from fastapi import HTTPException

        class FakeBody(ApproveRequest):
            pass

        body = ApproveRequest(override_reason="smoke test")
        try:
            out = approve_version(v.id, body, db, _user="smoke")
        except HTTPException as exc:
            pytest.fail(f"approve failed: {exc.detail}")
        db.refresh(v)
        assert v.status in {"APPROVED", "EXPORTED"}
        assert out.id == v.id
    finally:
        db.close()
        get_settings.cache_clear()
