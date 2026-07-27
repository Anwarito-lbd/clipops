"""Celery tasks for analyse → rank → generate → render pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.celery_app import celery
from app.config import get_settings
from app.db import (
    Campaign,
    CampaignRequirement,
    ClipCandidate,
    ClipVersion,
    ComplianceCheck,
    Render,
    SessionLocal,
    SocialAccount,
    SourceAsset,
)


def _run_module(module_path: Path, *args: str) -> dict:
    """Run a worker module as a script; fall back to importable helpers."""
    if module_path.exists():
        cmd = [sys.executable, str(module_path), *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                return json.loads(proc.stdout.strip().splitlines()[-1])
            except json.JSONDecodeError:
                pass
    return {}


@celery.task(name="clipops.process_asset")
def process_asset(asset_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        asset = db.get(SourceAsset, asset_id)
        if not asset:
            return {"error": "asset_not_found"}
        campaign = db.get(Campaign, asset.campaign_id)
        if not campaign:
            return {"error": "campaign_not_found"}

        storage_root = Path(settings.storage_root)
        if not storage_root.is_absolute():
            storage_root = ROOT / storage_root
        asset_path = storage_root / asset.storage_path
        work_dir = storage_root / "work" / asset.id
        work_dir.mkdir(parents=True, exist_ok=True)

        # --- Transcription (WhisperX worker; heuristic fallback) ---
        from workers.transcription.transcribe import transcribe_video

        transcript = transcribe_video(
            str(asset_path),
            str(work_dir / "transcript.json"),
            model=settings.whisperx_model,
            device=settings.whisperx_device,
            compute_type=settings.whisperx_compute_type,
        )
        asset.transcript_path = str(work_dir / "transcript.json")
        asset.status = "ANALYSED"
        db.commit()

        # --- Scene detection ---
        from workers.scene_detection.detect import detect_scenes

        scenes = detect_scenes(str(asset_path), str(work_dir / "scenes.json"))
        asset.scenes_path = str(work_dir / "scenes.json")
        db.commit()

        # --- Ranking ---
        from workers.clip_ranking.rank import rank_segments

        ranked = rank_segments(transcript, scenes, campaign_name=campaign.name)
        # Operator Mode: keep 10–20 candidates, select best 3–5, assign one account each (round-robin)
        keep_n = min(20, max(10, len(ranked)))
        top_pool = ranked[:keep_n]
        select_n = min(5, max(3, len(top_pool)))

        db.query(ClipCandidate).filter(ClipCandidate.source_asset_id == asset.id).delete()
        candidates: list[ClipCandidate] = []
        for i, seg in enumerate(top_pool, start=1):
            c = ClipCandidate(
                source_asset_id=asset.id,
                campaign_id=campaign.id,
                start_sec=seg["start_sec"],
                end_sec=seg["end_sec"],
                transcript_excerpt=seg.get("text"),
                scores=seg.get("scores", {}),
                total_score=seg.get("total_score", 0),
                rank=i,
                selected=i <= select_n,
            )
            db.add(c)
            candidates.append(c)
        db.commit()
        for c in candidates:
            db.refresh(c)

        # Snapshot requirements (immutable evidence)
        live_req = (
            db.query(CampaignRequirement)
            .filter(
                CampaignRequirement.campaign_id == campaign.id,
                CampaignRequirement.is_immutable_snapshot.is_(False),
            )
            .order_by(CampaignRequirement.created_at.desc())
            .first()
        )
        snapshot = None
        if live_req:
            snapshot = CampaignRequirement(
                campaign_id=campaign.id,
                required_hashtags=list(live_req.required_hashtags or []),
                required_tags=list(live_req.required_tags or []),
                required_disclosure=live_req.required_disclosure,
                disclosure_placement=live_req.disclosure_placement,
                min_duration_sec=live_req.min_duration_sec,
                max_duration_sec=live_req.max_duration_sec,
                aspect_ratio=live_req.aspect_ratio,
                forbidden_words=list(live_req.forbidden_words or []),
                forbidden_claims=list(live_req.forbidden_claims or []),
                requires_logo=live_req.requires_logo,
                requires_cta=live_req.requires_cta,
                cta_text=live_req.cta_text,
                posting_deadline=live_req.posting_deadline,
                no_external_music=live_req.no_external_music,
                extra=dict(live_req.extra or {}),
                is_immutable_snapshot=True,
                snapshot_at=datetime.now(timezone.utc),
            )
            db.add(snapshot)
            db.commit()
            db.refresh(snapshot)

        accounts = (
            db.query(SocialAccount)
            .filter(SocialAccount.platform == "tiktok", SocialAccount.is_active.is_(True))
            .order_by(SocialAccount.handle)
            .all()
        )
        if not accounts:
            asset.status = "FAILED"
            asset.error_message = "No TikTok accounts seeded"
            db.commit()
            return {"error": "no_accounts"}

        from workers.caption_generation.generate import generate_account_copy
        from workers.clip_ranking.hooks import classify_hook

        selected = [c for c in candidates if c.selected][:select_n]
        db.query(ClipVersion).filter(ClipVersion.campaign_id == campaign.id).delete()
        versions: list[ClipVersion] = []
        # Assign best clips to accounts round-robin — NOT 3 variants of every candidate
        for idx, cand in enumerate(selected):
            account = accounts[idx % len(accounts)]
            hook_type = classify_hook(cand.transcript_excerpt or "")
            copy = generate_account_copy(
                style=account.style or "dramatic",
                campaign_name=campaign.name,
                excerpt=cand.transcript_excerpt or "",
                hashtags=list((live_req.required_hashtags if live_req else []) or []),
                tags=list((live_req.required_tags if live_req else []) or []),
                disclosure=(live_req.required_disclosure if live_req else None),
                hook_variant=(idx % 3) + 1,
            )
            duration = float(cand.end_sec) - float(cand.start_sec)
            if duration <= 25:
                band = "15-25"
            elif duration <= 40:
                band = "25-40"
            else:
                band = "40-60"
            v = ClipVersion(
                candidate_id=cand.id,
                campaign_id=campaign.id,
                social_account_id=account.id,
                style=account.style or "dramatic",
                duration_band=band,
                hook_variant=(idx % 3) + 1,
                subtitle_style=["bold", "minimal"][idx % 2],
                caption=copy["caption"],
                hook_text=copy["hook"],
                context_intro=copy.get("context_intro") or hook_type,
                status="REVIEW_REQUIRED",
                requirements_snapshot_id=snapshot.id if snapshot else None,
            )
            db.add(v)
            versions.append(v)
        asset.status = "GENERATED"
        db.commit()

        # Production timeline events
        from app.db import ProductionEvent

        for title in (
            f"{len(candidates)} candidate clips generated",
            f"AI selected top {len(selected)}",
            f"{len(versions)} account versions ready for approval",
        ):
            db.add(
                ProductionEvent(
                    campaign_id=campaign.id,
                    source_asset_id=asset.id,
                    title=title,
                    status="done" if "ready" not in title else "action_required",
                )
            )
        db.commit()

        # Compliance gate for each version (pre-render)
        from packages.compliance_checker.checker import run_compliance_check

        for v in versions:
            db.refresh(v)
            req = snapshot or live_req
            result = run_compliance_check(
                campaign_name=campaign.name,
                expected_campaign_name=campaign.name,
                caption=v.caption or "",
                required_hashtags=list(req.required_hashtags) if req else [],
                required_tags=list(req.required_tags) if req else [],
                required_disclosure=req.required_disclosure if req else None,
                disclosure_in_video_start=True,
                duration_sec={"15-25": 20, "25-40": 32, "40-60": 50}[v.duration_band],
                min_duration_sec=req.min_duration_sec if req else 15,
                max_duration_sec=req.max_duration_sec if req else 60,
                aspect_ratio="9:16",
                forbidden_words=list(req.forbidden_words) if req else [],
                forbidden_claims=list(req.forbidden_claims) if req else [],
                has_external_music=False,
                export_hash=None,
                existing_hashes=[],
                requires_logo=bool(req.requires_logo) if req else False,
                has_logo=True,
                requires_cta=bool(req.requires_cta) if req else False,
                has_cta=True,
                posting_deadline=req.posting_deadline if req else None,
            )
            db.add(
                ComplianceCheck(
                    clip_version_id=v.id,
                    passed=result.passed,
                    checks=result.to_dict()["checks"],
                )
            )
        db.commit()
        return {"asset_id": asset_id, "candidates": len(candidates), "versions": len(versions)}
    except Exception as exc:  # noqa: BLE001
        asset = db.get(SourceAsset, asset_id)
        if asset:
            asset.status = "FAILED"
            asset.error_message = str(exc)
            db.commit()
        return {"error": str(exc)}
    finally:
        db.close()


@celery.task(name="clipops.render_version")
def render_version(clip_version_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        version = db.get(ClipVersion, clip_version_id)
        if not version:
            return {"error": "version_not_found"}
        if version.status not in {"APPROVED", "EXPORTED"}:
            return {"error": f"cannot_render_status_{version.status}"}

        campaign = db.get(Campaign, version.campaign_id)
        candidate = db.get(ClipCandidate, version.candidate_id)
        asset = db.get(SourceAsset, candidate.source_asset_id) if candidate else None
        if not asset or not campaign:
            return {"error": "missing_asset_or_campaign"}

        accounts = (
            db.query(SocialAccount)
            .filter(SocialAccount.platform == "tiktok")
            .order_by(SocialAccount.handle)
            .all()
        )
        slot_map = {a.id: i + 1 for i, a in enumerate(accounts[:3])}
        slot = slot_map.get(version.social_account_id, 1)

        storage_root = Path(settings.storage_root)
        if not storage_root.is_absolute():
            storage_root = ROOT / storage_root
        package_dir = storage_root / "exports" / campaign.id / f"account-{slot}"
        package_dir.mkdir(parents=True, exist_ok=True)

        from workers.video_rendering.render import render_account_package

        source = storage_root / asset.storage_path
        result = render_account_package(
            source_video=str(source),
            start_sec=candidate.start_sec,
            end_sec=candidate.end_sec,
            style=version.style,
            duration_band=version.duration_band,
            caption=version.caption or "",
            hook_text=version.hook_text or "",
            package_dir=str(package_dir),
            ffmpeg_path=settings.ffmpeg_path,
            auto_editor=settings.auto_editor_enabled,
        )

        content_hash = None
        video_path = Path(result["video_path"])
        if video_path.exists():
            content_hash = hashlib.sha256(video_path.read_bytes()).hexdigest()

        # Duplicate check across renders
        existing = [r.content_hash for r in db.query(Render).all() if r.content_hash]
        from packages.compliance_checker.checker import run_compliance_check

        req = None
        if version.requirements_snapshot_id:
            req = db.get(CampaignRequirement, version.requirements_snapshot_id)

        compliance = run_compliance_check(
            campaign_name=campaign.name,
            expected_campaign_name=campaign.name,
            caption=version.caption or "",
            required_hashtags=list(req.required_hashtags) if req else [],
            required_tags=list(req.required_tags) if req else [],
            required_disclosure=req.required_disclosure if req else None,
            disclosure_in_video_start=True,
            duration_sec=result.get("duration_sec", 20),
            min_duration_sec=req.min_duration_sec if req else 15,
            max_duration_sec=req.max_duration_sec if req else 60,
            aspect_ratio="9:16",
            forbidden_words=list(req.forbidden_words) if req else [],
            forbidden_claims=list(req.forbidden_claims) if req else [],
            has_external_music=False,
            export_hash=content_hash,
            existing_hashes=[h for h in existing if h != content_hash],
            requires_logo=bool(req.requires_logo) if req else False,
            has_logo=True,
            requires_cta=bool(req.requires_cta) if req else False,
            has_cta=True,
            posting_deadline=req.posting_deadline if req else None,
        )

        checklist_path = package_dir / "compliance-checklist.json"
        checklist_path.write_text(json.dumps(compliance.to_dict(), indent=2), encoding="utf-8")

        render = Render(
            clip_version_id=version.id,
            account_slot=slot,
            video_path=result["video_path"],
            caption_path=result["caption_path"],
            cover_path=result.get("cover_path"),
            checklist_path=str(checklist_path),
            package_dir=str(package_dir),
            content_hash=content_hash,
            status="EXPORTED" if compliance.passed else "REVIEW_REQUIRED",
        )
        db.add(render)
        db.add(
            ComplianceCheck(
                clip_version_id=version.id,
                passed=compliance.passed,
                checks=compliance.to_dict()["checks"],
            )
        )
        if compliance.passed:
            version.status = "EXPORTED"
        db.commit()
        return {"render_id": render.id, "package_dir": str(package_dir), "passed": compliance.passed}
    except Exception as exc:  # noqa: BLE001
        version = db.get(ClipVersion, clip_version_id)
        if version:
            version.status = "FAILED"
            db.commit()
        return {"error": str(exc)}
    finally:
        db.close()
