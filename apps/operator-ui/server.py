"""Lightweight FastAPI server for the ClipOps Operator Studio UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from studio import StudioService, check_media_engines  # noqa: E402


def _workspace_root() -> Path:
    custom = os.environ.get("CLIPOPS_STUDIO_WORKSPACE")
    return Path(custom) if custom else ROOT / "storage" / "operator_studio"


def get_service() -> StudioService:
    return StudioService(_workspace_root())


class DemoSessionRequest(BaseModel):
    title: str = "Creator Studio Demo (24s Multi-Scene)"
    campaign_name: str = "Creator Showcase"
    auto_run: bool = True


class OpenVideoRequest(BaseModel):
    video_path: str
    title: str | None = None
    campaign_name: str = "Creator Showcase"


class TranscribeRequest(BaseModel):
    model: str = "tiny"
    device: str = "cpu"
    compute_type: str = "int8"


class SceneDetectRequest(BaseModel):
    detector: str = Field(default="hybrid", pattern="^(content|adaptive|hybrid)$")
    content_threshold: float = 27.0
    adaptive_threshold: float = 3.0


class ScoreRequest(BaseModel):
    campaign_name: str | None = None
    preferred_length_band: str = Field(default="15-25", pattern="^(15-25|25-40|40-60)$")


class ClipDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED|PENDING)$")
    notes: str = ""
    start_sec: float | None = None
    end_sec: float | None = None
    style: str | None = None
    duration_band: str | None = None
    hook_text: str | None = None
    caption: str | None = None


class RenderRequest(BaseModel):
    style: str | None = None
    duration_band: str | None = None
    hook_text: str | None = None
    burn_captions: bool = True


app = FastAPI(
    title="ClipOps Operator Studio",
    version="1.0.0",
    description="Ethical short-form video clipping & editing workstation with human approval gates.",
)

STATIC_DIR = HERE / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="studio-static")


@app.get("/", response_class=HTMLResponse)
def studio_index() -> HTMLResponse:
    index_file = STATIC_DIR / "index.html"
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/logo.png")
def studio_logo() -> FileResponse:
    candidates = [ROOT / "ui" / "logo.png", ROOT / "docs" / "images" / "clipops-logo.png"]
    for c in candidates:
        if c.exists():
            return FileResponse(c, media_type="image/png")
    raise HTTPException(404, "Logo not found")


@app.get("/api/studio/health")
def studio_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "clipops-operator-studio",
        "workspace_root": str(_workspace_root()),
        "engines": check_media_engines(),
    }


@app.get("/api/studio/sessions")
def list_sessions() -> list[dict[str, Any]]:
    return get_service().list_sessions()


@app.post("/api/studio/sessions/demo")
def create_demo_session(body: DemoSessionRequest) -> dict[str, Any]:
    try:
        return get_service().create_demo_session(
            title=body.title,
            campaign_name=body.campaign_name,
            auto_run=body.auto_run,
        )
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/studio/sessions/open")
def open_video_session(body: OpenVideoRequest) -> dict[str, Any]:
    try:
        return get_service().open_video_session(
            body.video_path,
            title=body.title,
            campaign_name=body.campaign_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/studio/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    try:
        return get_service().get_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/studio/sessions/{session_id}/transcribe")
def run_transcribe(session_id: str, body: TranscribeRequest) -> dict[str, Any]:
    try:
        return get_service().step_transcribe(
            session_id,
            model=body.model,
            device=body.device,
            compute_type=body.compute_type,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/studio/sessions/{session_id}/scenes")
def run_scenes(session_id: str, body: SceneDetectRequest) -> dict[str, Any]:
    try:
        return get_service().step_detect_scenes(
            session_id,
            detector=body.detector,
            content_threshold=body.content_threshold,
            adaptive_threshold=body.adaptive_threshold,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/studio/sessions/{session_id}/score")
def run_score(session_id: str, body: ScoreRequest) -> dict[str, Any]:
    try:
        return get_service().step_score_hooks(
            session_id,
            campaign_name=body.campaign_name,
            preferred_length_band=body.preferred_length_band,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/studio/sessions/{session_id}/clips/{clip_id}/decision")
def decide_clip(session_id: str, clip_id: str, body: ClipDecisionRequest) -> dict[str, Any]:
    try:
        return get_service().decide_clip(
            session_id,
            clip_id,
            decision=body.decision,
            notes=body.notes,
            start_sec=body.start_sec,
            end_sec=body.end_sec,
            style=body.style,
            duration_band=body.duration_band,
            hook_text=body.hook_text,
            caption=body.caption,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/studio/sessions/{session_id}/clips/{clip_id}/dry-run")
def dry_run_clip(session_id: str, clip_id: str, body: RenderRequest) -> dict[str, Any]:
    try:
        return get_service().dry_run_render(
            session_id,
            clip_id,
            style=body.style,
            duration_band=body.duration_band,
            hook_text=body.hook_text,
            burn_captions=body.burn_captions,
        )
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/studio/sessions/{session_id}/clips/{clip_id}/render")
def render_clip(session_id: str, clip_id: str, body: RenderRequest) -> dict[str, Any]:
    try:
        return get_service().execute_render(
            session_id,
            clip_id,
            style=body.style,
            duration_band=body.duration_band,
            hook_text=body.hook_text,
            burn_captions=body.burn_captions,
        )
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/studio/media/{session_id}/{rel_path:path}")
def stream_media(session_id: str, rel_path: str) -> FileResponse:
    sdir = (_workspace_root() / "".join(c for c in session_id if c.isalnum() or c in "-_")).resolve()
    target = (sdir / rel_path).resolve()
    if not str(target).startswith(str(sdir)) or not target.exists() or not target.is_file():
        raise HTTPException(404, "Media not found")
    if target.suffix.lower() not in {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".json", ".txt"}:
        raise HTTPException(400, "Unsupported media extension")
    return FileResponse(target)
