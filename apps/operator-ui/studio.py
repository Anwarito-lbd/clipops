"""Stateful local StudioService powering the ClipOps Operator UI & CLI."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.compliance_checker.checker import run_compliance_check
from packages.services.clip_ranking import ClipRankingService, compute_retention_pacing
from packages.shared_types.constants import ACCOUNT_STYLES, DURATION_BANDS
from workers.caption_generation.generate import generate_account_copy
from workers.clip_ranking.hooks import classify_hook
from workers.scene_detection.detect import detect_scenes
from workers.transcription.transcribe import transcribe_video
from workers.video_rendering.render import build_filtergraph, render_account_package


DEFAULT_DEMO_SCRIPT = [
    {
        "start": 0.0,
        "end": 8.0,
        "text": "Wait until you see this workflow mistake most creators miss in their first 3 seconds.",
        "speaker": "SPEAKER_0",
    },
    {
        "start": 8.0,
        "end": 16.0,
        "text": "Here is the surprising fact: tight scene cuts and clean loudness pacing change retention.",
        "speaker": "SPEAKER_0",
    },
    {
        "start": 16.0,
        "end": 24.0,
        "text": "So finally here is the payoff — preview every cut, verify compliance, then publish manually.",
        "speaker": "SPEAKER_0",
    },
]


def _word_timestamps_from_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg in segments:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.0))
        tokens = (seg.get("text") or "").split()
        if not tokens:
            continue
        step = max(0.12, (end - start) / len(tokens))
        t = start
        for tok in tokens:
            w_end = min(end, round(t + step * 0.9, 3))
            words.append({"word": tok, "start": round(t, 3), "end": max(round(t + 0.05, 3), w_end)})
            t += step
    return words


def probe_media(video_path: str) -> dict[str, Any]:
    """Inspect duration, resolution, codec, and byte size using ffprobe."""
    p = Path(video_path)
    info: dict[str, Any] = {
        "exists": p.exists(),
        "filename": p.name,
        "bytes": p.stat().st_size if p.exists() else 0,
        "duration_sec": 0.0,
        "width": None,
        "height": None,
        "video_codec": None,
        "audio_codec": None,
        "fps": None,
    }
    if not p.exists() or not shutil.which("ffprobe"):
        return info
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
                "-of",
                "json",
                str(p),
            ],
            text=True,
        )
        parsed = json.loads(raw or "{}")
        fmt = parsed.get("format") or {}
        if fmt.get("duration"):
            info["duration_sec"] = round(float(fmt["duration"]), 3)
        for stream in parsed.get("streams") or []:
            if stream.get("codec_type") == "video" and not info["video_codec"]:
                info["video_codec"] = stream.get("codec_name")
                info["width"] = stream.get("width")
                info["height"] = stream.get("height")
                rate = stream.get("r_frame_rate") or ""
                if "/" in rate:
                    num, den = rate.split("/", 1)
                    if float(den) > 0:
                        info["fps"] = round(float(num) / float(den), 2)
            elif stream.get("codec_type") == "audio" and not info["audio_codec"]:
                info["audio_codec"] = stream.get("codec_name")
    except Exception:
        pass
    return info


def synthesize_demo_video(dest_mp4: Path, duration_per_scene: int = 8) -> Path:
    """Create a 24s 3-scene 1080x1920 synthetic MP4 using FFmpeg lavfi sources."""
    dest_mp4.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg binary not found on PATH")

    # 3 distinct high-contrast scenes so PySceneDetect detects real visual cuts cleanly
    d = max(4, int(duration_per_scene))
    total = d * 3
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x0f172a:s=1080x1920:r=30:d={d}",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x0e7490:s=1080x1920:r=30:d={d}",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x4338ca:s=1080x1920:r=30:d={d}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={total}",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(dest_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return dest_mp4


def check_media_engines() -> dict[str, Any]:
    """Inspect local availability of FFmpeg, PySceneDetect, WhisperX, faster-whisper, and Remotion."""
    import importlib.util

    has_ffmpeg = bool(shutil.which("ffmpeg"))
    has_ffprobe = bool(shutil.which("ffprobe"))
    has_scenedetect = importlib.util.find_spec("scenedetect") is not None
    has_whisperx = importlib.util.find_spec("whisperx") is not None
    has_faster_whisper = importlib.util.find_spec("faster_whisper") is not None
    remotion_url = os.environ.get("REMOTION_URL", "").strip()
    remotion_up = False
    if remotion_url:
        try:
            import urllib.request

            with urllib.request.urlopen(remotion_url.rstrip("/") + "/health", timeout=1.5) as resp:
                remotion_up = resp.status == 200
        except Exception:
            remotion_up = False

    return {
        "ffmpeg": has_ffmpeg,
        "ffprobe": has_ffprobe,
        "pyscenedetect": has_scenedetect,
        "whisperx": has_whisperx,
        "faster_whisper": has_faster_whisper,
        "remotion": remotion_up,
        "remotion_url": remotion_url or None,
        "automation_boundary": "human_approval_manual_publish",
    }


class StudioService:
    """File-backed session store and step-by-step clipping workstation."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = (
            Path(workspace_root)
            if workspace_root
            else ROOT / "storage" / "operator_studio"
        )
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        if not safe_id:
            raise ValueError("Invalid session_id")
        return self.workspace_root / safe_id

    def _session_file(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    def list_sessions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for child in sorted(self.workspace_root.iterdir(), reverse=True):
            sf = child / "session.json"
            if child.is_dir() and sf.exists():
                try:
                    data = json.loads(sf.read_text(encoding="utf-8"))
                    out.append(
                        {
                            "session_id": data["session_id"],
                            "title": data.get("title"),
                            "source_filename": (data.get("probe") or {}).get("filename"),
                            "duration_sec": (data.get("probe") or {}).get("duration_sec"),
                            "steps": data.get("steps"),
                            "clip_count": len(data.get("clips") or []),
                            "created_at": data.get("created_at"),
                        }
                    )
                except Exception:
                    continue
        return out

    def get_session(self, session_id: str) -> dict[str, Any]:
        sf = self._session_file(session_id)
        if not sf.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return json.loads(sf.read_text(encoding="utf-8"))

    def _save_session(self, data: dict[str, Any]) -> dict[str, Any]:
        sdir = self._session_dir(data["session_id"])
        sdir.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._session_file(data["session_id"]).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        return data

    def create_demo_session(
        self,
        *,
        title: str = "Creator Studio Demo (24s Multi-Scene)",
        campaign_name: str = "Creator Showcase",
        auto_run: bool = False,
    ) -> dict[str, Any]:
        session_id = f"demo-{uuid4().hex[:8]}"
        sdir = self._session_dir(session_id)
        sdir.mkdir(parents=True, exist_ok=True)
        src_path = synthesize_demo_video(sdir / "source_demo.mp4", duration_per_scene=8)
        session = self._init_session_record(
            session_id=session_id,
            title=title,
            source_path=src_path,
            campaign_name=campaign_name,
            is_synthetic_demo=True,
        )
        if auto_run:
            self.step_transcribe(session_id, model="tiny", device="cpu", compute_type="int8")
            self.step_detect_scenes(session_id, detector="content")
            session = self.step_score_hooks(session_id, campaign_name=campaign_name)
        return session

    def open_video_session(
        self,
        video_path: str,
        *,
        title: str | None = None,
        campaign_name: str = "Creator Showcase",
    ) -> dict[str, Any]:
        src = Path(video_path).expanduser().resolve()
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        session_id = f"clip-{uuid4().hex[:8]}"
        sdir = self._session_dir(session_id)
        sdir.mkdir(parents=True, exist_ok=True)
        local_copy = sdir / f"source{src.suffix.lower() or '.mp4'}"
        shutil.copy2(src, local_copy)
        return self._init_session_record(
            session_id=session_id,
            title=title or src.name,
            source_path=local_copy,
            campaign_name=campaign_name,
            is_synthetic_demo=False,
        )

    def _init_session_record(
        self,
        *,
        session_id: str,
        title: str,
        source_path: Path,
        campaign_name: str,
        is_synthetic_demo: bool,
    ) -> dict[str, Any]:
        probe = probe_media(str(source_path))
        sdir = self._session_dir(session_id)
        rel_source = source_path.relative_to(sdir).as_posix()
        data: dict[str, Any] = {
            "session_id": session_id,
            "title": title,
            "campaign_name": campaign_name,
            "is_synthetic_demo": is_synthetic_demo,
            "source_path": str(source_path),
            "source_media_url": f"/api/studio/media/{session_id}/{rel_source}",
            "probe": probe,
            "steps": {
                "probe": True,
                "transcribe": False,
                "scenes": False,
                "score": False,
                "render": False,
            },
            "transcript": None,
            "scenes": None,
            "clips": [],
            "renders": {},
            "dry_runs": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._save_session(data)

    def step_transcribe(
        self,
        session_id: str,
        *,
        model: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> dict[str, Any]:
        data = self.get_session(session_id)
        sdir = self._session_dir(session_id)
        out_json = sdir / "transcript.json"
        payload = transcribe_video(
            data["source_path"],
            str(out_json),
            model=model,
            device=device,
            compute_type=compute_type,
            hf_token=os.environ.get("HF_TOKEN"),
            enable_diarization=False,
        )
        # For synthetic silent/tone demo runs, enrich the heuristic fallback with realistic demo lines
        # while truthfully recording the underlying ASR engine + fallback_reason.
        if data.get("is_synthetic_demo") and payload.get("engine") == "heuristic":
            payload["segments"] = DEFAULT_DEMO_SCRIPT
            payload["word_segments"] = _word_timestamps_from_segments(DEFAULT_DEMO_SCRIPT)
            payload["demo_script_overlay"] = True
            out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        data["transcript"] = payload
        data["steps"]["transcribe"] = True
        return self._save_session(data)

    def step_detect_scenes(
        self,
        session_id: str,
        *,
        detector: str = "hybrid",
        content_threshold: float = 27.0,
        adaptive_threshold: float = 3.0,
    ) -> dict[str, Any]:
        data = self.get_session(session_id)
        sdir = self._session_dir(session_id)
        out_json = sdir / "scenes.json"
        payload = detect_scenes(
            data["source_path"],
            str(out_json),
            detector=detector,
            content_threshold=content_threshold,
            adaptive_threshold=adaptive_threshold,
        )
        data["scenes"] = payload
        data["steps"]["scenes"] = True
        return self._save_session(data)

    def step_score_hooks(
        self,
        session_id: str,
        *,
        campaign_name: str | None = None,
        preferred_length_band: str = "15-25",
    ) -> dict[str, Any]:
        data = self.get_session(session_id)
        if not data.get("transcript"):
            data = self.step_transcribe(session_id)
        if not data.get("scenes"):
            data = self.step_detect_scenes(session_id)

        camp = campaign_name or data.get("campaign_name") or "Creator Showcase"
        data["campaign_name"] = camp
        ranked = ClipRankingService().rank_footage(
            data["transcript"],
            data["scenes"],
            campaign_name=camp,
            keep=20,
            select=5,
            preferred_length_band=preferred_length_band,
        )

        # Preserve prior human approve/reject decisions if re-scoring
        prior_decisions = {
            c["clip_id"]: {
                "decision": c.get("decision", "PENDING"),
                "decision_notes": c.get("decision_notes", ""),
            }
            for c in data.get("clips") or []
        }

        clips: list[dict[str, Any]] = []
        for idx, cand in enumerate(ranked["candidates"]):
            clip_id = f"clip-{idx + 1}"
            style = ACCOUNT_STYLES[idx % len(ACCOUNT_STYLES)]
            hook_type = cand.get("hook_type") or classify_hook(cand.get("text") or "")
            copy = generate_account_copy(
                style=style,
                campaign_name=camp,
                excerpt=cand.get("text") or "",
                hashtags=["#CreatorStudio", f"#{camp.replace(' ', '')}"],
                tags=[],
                disclosure="Paid partnership",
                hook_variant=(idx % 3) + 1,
            )
            dur = round(float(cand["end_sec"]) - float(cand["start_sec"]), 3)
            pacing = cand.get("retention_pacing") or compute_retention_pacing(
                cand.get("text") or "", dur
            )
            prior = prior_decisions.get(clip_id, {})
            clips.append(
                {
                    "clip_id": clip_id,
                    "rank": idx + 1,
                    "selected_for_batch": idx < ranked["select_n"],
                    "start_sec": round(float(cand["start_sec"]), 3),
                    "end_sec": round(float(cand["end_sec"]), 3),
                    "duration_sec": dur,
                    "duration_band": cand.get("duration_band", "15-25"),
                    "style": style,
                    "hook_type": hook_type,
                    "hook_text": copy["hook"],
                    "caption": copy["caption"],
                    "transcript_excerpt": cand.get("text") or "",
                    "total_score": cand["total_score"],
                    "rank_report": cand["rank_report"],
                    "retention_pacing": pacing,
                    "decision": prior.get("decision", "PENDING"),
                    "decision_notes": prior.get("decision_notes", ""),
                }
            )

        data["clips"] = clips
        data["steps"]["score"] = True
        return self._save_session(data)

    def _find_clip(self, data: dict[str, Any], clip_id: str) -> dict[str, Any]:
        for clip in data.get("clips") or []:
            if clip["clip_id"] == clip_id:
                return clip
        raise KeyError(f"Clip not found: {clip_id}")

    def decide_clip(
        self,
        session_id: str,
        clip_id: str,
        *,
        decision: str,
        notes: str = "",
        start_sec: float | None = None,
        end_sec: float | None = None,
        style: str | None = None,
        duration_band: str | None = None,
        hook_text: str | None = None,
        caption: str | None = None,
    ) -> dict[str, Any]:
        norm = decision.upper().strip()
        if norm not in {"APPROVED", "REJECTED", "PENDING"}:
            raise ValueError(f"Invalid decision: {decision}")
        data = self.get_session(session_id)
        clip = self._find_clip(data, clip_id)

        if start_sec is not None:
            clip["start_sec"] = round(max(0.0, float(start_sec)), 3)
        if end_sec is not None:
            clip["end_sec"] = round(max(clip["start_sec"] + 0.5, float(end_sec)), 3)
        clip["duration_sec"] = round(clip["end_sec"] - clip["start_sec"], 3)

        if style and style in ACCOUNT_STYLES:
            clip["style"] = style
        if duration_band and duration_band in DURATION_BANDS:
            clip["duration_band"] = duration_band
        if hook_text is not None:
            clip["hook_text"] = hook_text.strip()
        if caption is not None:
            clip["caption"] = caption

        clip["decision"] = norm
        clip["decision_notes"] = notes
        clip["compliance"] = self._evaluate_clip_compliance(data, clip)
        return self._save_session(data)

    def _evaluate_clip_compliance(
        self, data: dict[str, Any], clip: dict[str, Any], *, min_sec: int = 5, max_sec: int = 60
    ) -> dict[str, Any]:
        existing_hashes = [
            r.get("sha256")
            for cid, r in (data.get("renders") or {}).items()
            if cid != clip["clip_id"] and r.get("sha256")
        ]
        render_info = (data.get("renders") or {}).get(clip["clip_id"]) or {}
        export_hash = render_info.get("sha256") or hashlib.sha256(
            f"{clip['clip_id']}:{clip['start_sec']}:{clip['end_sec']}:{clip['style']}".encode()
        ).hexdigest()
        res = run_compliance_check(
            campaign_name=data.get("campaign_name") or "Creator Showcase",
            expected_campaign_name=data.get("campaign_name") or "Creator Showcase",
            caption=clip.get("caption") or "",
            required_hashtags=[],
            required_tags=[],
            required_disclosure="Paid partnership",
            disclosure_in_video_start=True,
            duration_sec=float(clip["duration_sec"]),
            min_duration_sec=min_sec,
            max_duration_sec=max_sec,
            aspect_ratio="9:16",
            forbidden_words=[],
            forbidden_claims=[],
            has_external_music=False,
            export_hash=export_hash,
            existing_hashes=existing_hashes,
            requires_logo=False,
            has_logo=True,
            requires_cta=False,
            has_cta=True,
            posting_deadline=None,
        )
        return res.to_dict()

    def dry_run_render(
        self,
        session_id: str,
        clip_id: str,
        *,
        style: str | None = None,
        duration_band: str | None = None,
        hook_text: str | None = None,
        burn_captions: bool = True,
    ) -> dict[str, Any]:
        data = self.get_session(session_id)
        clip = self._find_clip(data, clip_id)
        eff_style = style if style in ACCOUNT_STYLES else clip["style"]
        eff_band = duration_band if duration_band in DURATION_BANDS else clip["duration_band"]
        eff_hook = hook_text if hook_text is not None else clip["hook_text"]
        sdir = self._session_dir(session_id)
        pkg_dir = sdir / "exports" / clip_id / eff_style
        out_mp4 = pkg_dir / "video.mp4"

        fg = build_filtergraph(
            source_video=data["source_path"],
            start_sec=float(clip["start_sec"]),
            end_sec=float(clip["end_sec"]),
            style=eff_style,
            duration_band=eff_band,
            hook_text=eff_hook,
            output_path=str(pkg_dir / "base_cut.mp4"),
            burn_captions=burn_captions,
        )
        remotion_payload = {
            "endpoint": os.environ.get("REMOTION_URL") or "http://127.0.0.1:3100/render (optional)",
            "composition": eff_style.capitalize(),
            "props": {
                "style": eff_style,
                "hookText": eff_hook,
                "caption": clip["caption"],
                "inputVideo": str(pkg_dir / "base_cut.mp4"),
                "outputPath": str(pkg_dir / "video_remotion.mp4"),
            },
        }
        compliance = self._evaluate_clip_compliance(data, clip)
        dry_run = {
            "mode": "dry_run",
            "clip_id": clip_id,
            "package_dir": str(pkg_dir),
            "target_video_path": str(out_mp4),
            "burn_captions": burn_captions,
            "ffmpeg": fg,
            "command_preview": " ".join(
                f'"{part}"' if (" " in part or "=" in part or "," in part) else part
                for part in fg["command"]
            ),
            "remotion_payload": remotion_payload,
            "compliance_preview": compliance,
        }
        data.setdefault("dry_runs", {})[clip_id] = dry_run
        self._save_session(data)
        return dry_run

    def execute_render(
        self,
        session_id: str,
        clip_id: str,
        *,
        style: str | None = None,
        duration_band: str | None = None,
        hook_text: str | None = None,
        burn_captions: bool = True,
    ) -> dict[str, Any]:
        data = self.get_session(session_id)
        clip = self._find_clip(data, clip_id)
        eff_style = style if style in ACCOUNT_STYLES else clip["style"]
        eff_band = duration_band if duration_band in DURATION_BANDS else clip["duration_band"]
        eff_hook = hook_text if hook_text is not None else clip["hook_text"]
        clip["style"] = eff_style
        clip["duration_band"] = eff_band
        clip["hook_text"] = eff_hook

        sdir = self._session_dir(session_id)
        pkg_dir = sdir / "exports" / clip_id / eff_style
        remotion_url = os.environ.get("REMOTION_URL", "").strip() or None
        res = render_account_package(
            source_video=data["source_path"],
            start_sec=float(clip["start_sec"]),
            end_sec=float(clip["end_sec"]),
            style=eff_style,
            duration_band=eff_band,
            caption=clip["caption"],
            hook_text=eff_hook,
            package_dir=str(pkg_dir),
            remotion_url=remotion_url,
            burn_captions=burn_captions,
        )
        video_path = Path(res["video_path"])
        sha256 = hashlib.sha256(video_path.read_bytes()).hexdigest() if res["ok"] else None
        probe = probe_media(str(video_path)) if res["ok"] else {}
        rel_video = video_path.relative_to(sdir).as_posix() if video_path.exists() else None
        cover_path = Path(res["cover_path"])
        rel_cover = cover_path.relative_to(sdir).as_posix() if cover_path.exists() and cover_path.stat().st_size > 0 else None

        render_record = {
            **res,
            "style": eff_style,
            "duration_band": eff_band,
            "sha256": sha256,
            "probe": probe,
            "video_url": f"/api/studio/media/{session_id}/{rel_video}" if rel_video else None,
            "cover_url": f"/api/studio/media/{session_id}/{rel_cover}" if rel_cover else None,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
        }
        data.setdefault("renders", {})[clip_id] = render_record
        data["steps"]["render"] = True
        clip["compliance"] = self._evaluate_clip_compliance(data, clip)
        self._save_session(data)
        return render_record
