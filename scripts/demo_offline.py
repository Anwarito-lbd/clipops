#!/usr/bin/env python3
"""Self-contained ClipOps sample. No API keys, Redis, GPU, or Remotion.

Builds a short synthetic 9:16 clip, then runs the same worker functions the
API uses: transcription fallback, scene detection, ranking, captions,
compliance, and the FFmpeg account package.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.campaign_parser.parser import parse_campaign_brief
from packages.compliance_checker.checker import run_compliance_check
from packages.services.campaign_scoring import CampaignScoringService
from packages.services.clip_ranking import ClipRankingService
from workers.caption_generation.generate import generate_account_copy
from workers.scene_detection.detect import detect_scenes
from workers.transcription.transcribe import transcribe_video
from workers.video_rendering.render import render_account_package

BRIEF = """VoltPop Summer Push
CPM: $8.50
Budget: $25000 utilised 40%
Geo: US CA
Duration: 20-45 seconds
#VoltPop #ContentRewards @voltpop
Disclosure: Paid partnership
"""


def _ffmpeg_sample(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Three hard cuts so scene detection has something to split.
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1e3a5f:s=1080x1920:d=4",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x7f1d1d:s=1080x1920:d=4",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x14532d:s=1080x1920:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=12",
            "-filter_complex",
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
            "-map",
            "[v]",
            "-map",
            "3:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _ffprobe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "proof"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    source = work / "sample-source.mp4"
    print("generating synthetic 1080x1920 source")
    _ffmpeg_sample(source)

    print("transcribing (WhisperX → faster-whisper → heuristic)")
    transcript = transcribe_video(
        str(source),
        str(work / "transcript.json"),
        model="tiny",
        device="cpu",
        compute_type="int8",
        hf_token=None,
        enable_diarization=False,
    )
    print("detecting scenes")
    scenes = detect_scenes(str(source), str(work / "scenes.json"))

    parsed = parse_campaign_brief(BRIEF)
    score = CampaignScoringService().score(
        campaign_id="demo-voltpop",
        cpm=parsed.cpm,
        total_budget=parsed.total_budget,
        budget_utilised=parsed.budget_utilised,
        required_geo=parsed.required_geo,
        has_rights=parsed.has_rights,
    )
    ranked = ClipRankingService().rank_footage(
        transcript,
        scenes,
        campaign_name=parsed.name,
        keep=20,
        select=3,
    )
    selected = ranked["selected"]
    copy = generate_account_copy(
        style="dramatic",
        campaign_name=parsed.name,
        excerpt=selected[0].get("text") or "",
        hashtags=parsed.required_hashtags,
        tags=parsed.required_tags,
        disclosure=parsed.required_disclosure,
        hook_variant=1,
    )
    package_dir = work / "account-1"
    rendered = render_account_package(
        source_video=str(source),
        start_sec=float(selected[0]["start_sec"]),
        end_sec=float(selected[0]["end_sec"]),
        style="dramatic",
        duration_band="15-25",
        caption=copy["caption"],
        hook_text=copy["hook"],
        package_dir=str(package_dir),
        ffmpeg_path="ffmpeg",
        auto_editor=False,
        remotion_url=None,
        burn_captions=True,
    )
    video = Path(rendered["video_path"])
    compliance = run_compliance_check(
        campaign_name=parsed.name,
        expected_campaign_name=parsed.name,
        caption=copy["caption"],
        required_hashtags=parsed.required_hashtags,
        required_tags=parsed.required_tags,
        required_disclosure=parsed.required_disclosure,
        disclosure_in_video_start=None,
        duration_sec=float(rendered["duration_sec"]),
        min_duration_sec=parsed.min_duration_sec,
        max_duration_sec=parsed.max_duration_sec,
        aspect_ratio="9:16",
        forbidden_words=[],
        forbidden_claims=[],
        has_external_music=False,
        export_hash="demo",
        existing_hashes=[],
        requires_logo=False,
        has_logo=None,
        requires_cta=False,
        has_cta=None,
        posting_deadline=None,
    )
    frame = out_dir / "sample-frame.png"
    if video.exists() and video.stat().st_size > 0:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "0.4",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(frame),
            ],
            check=True,
            capture_output=True,
        )
        probe = _ffprobe(video)
    else:
        probe = {}

    summary = {
        "source": {
            "path": str(source),
            "bytes": source.stat().st_size,
            "probe": _ffprobe(source),
        },
        "transcript": {
            "engine": transcript.get("engine"),
            "fallback_reason": transcript.get("fallback_reason"),
            "segment_count": len(transcript.get("segments") or []),
            "first_text": (transcript.get("segments") or [{}])[0].get("text"),
        },
        "scenes": {
            "engine": scenes.get("engine"),
            "count": len(scenes.get("scenes") or []),
            "windows": scenes.get("scenes"),
        },
        "campaign": {
            "name": parsed.name,
            "cpm": parsed.cpm,
            "hashtags": parsed.required_hashtags,
            "tags": parsed.required_tags,
            "duration": [parsed.min_duration_sec, parsed.max_duration_sec],
            "score": score.score,
            "recommendation": score.recommendation,
            "reject_reasons": score.reject_reasons,
        },
        "ranking": {
            "candidate_count": len(ranked["candidates"]),
            "select_n": ranked["select_n"],
            "selected": [
                {
                    "start_sec": s["start_sec"],
                    "end_sec": s["end_sec"],
                    "total_score": s["total_score"],
                    "hook_type": (s.get("rank_report") or {}).get("hook_type"),
                    "predicted_performance": (s.get("rank_report") or {}).get(
                        "predicted_performance"
                    ),
                    "text": s.get("text"),
                }
                for s in selected
            ],
        },
        "copy": copy,
        "render": {
            "ok": rendered.get("ok"),
            "duration_sec": rendered.get("duration_sec"),
            "video_bytes": video.stat().st_size if video.exists() else 0,
            "probe": probe,
            "meta": json.loads((package_dir / "render-meta.json").read_text(encoding="utf-8")),
        },
        "compliance": compliance.to_dict(),
        "frame": str(frame) if frame.exists() else None,
    }
    dest = out_dir / "demo-summary.json"
    dest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {dest}")
    return 0 if rendered.get("ok") and frame.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
