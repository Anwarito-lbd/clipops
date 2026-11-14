"""Tests for ClipOps Operator Studio UI/CLI, adaptive scene detection, retention pacing, and Obsidian vault graph."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STUDIO_DIR = ROOT / "apps" / "operator-ui"
for p in (str(ROOT), str(STUDIO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.services.clip_ranking import compute_retention_pacing  # noqa: E402
from workers.scene_detection.detect import detect_scenes  # noqa: E402
from workers.video_rendering.render import _wrap_drawtext_lines, build_filtergraph  # noqa: E402


def test_retention_pacing_math():
    words = [
        {"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3}
        for i, w in enumerate("Wait until you see this surprising payoff right now today".split())
    ]
    pacing = compute_retention_pacing(
        "Wait until you see this surprising payoff right now today",
        duration_sec=10.0,
        word_segments=words,
        start_sec=0.0,
        end_sec=10.0,
    )
    assert pacing["word_count"] == 10
    assert pacing["wpm"] == 60.0
    assert pacing["hook_window_words_3s"] == 8
    assert pacing["spoken_sec"] == 3.0
    assert pacing["dead_air_sec"] == 7.0
    assert pacing["dead_air_ratio"] == 0.7
    assert pacing["pacing_label"] == "SPARSE_LOW_SPEECH"


def test_build_filtergraph_dry_run():
    long_hook = "Wait until you see this workflow mistake most creators miss in their first 3 seconds"
    wrapped = _wrap_drawtext_lines(long_hook, max_chars=26, max_lines=3)
    assert 2 <= len(wrapped) <= 3
    assert all(len(line) <= 29 for line in wrapped)

    fg = build_filtergraph(
        source_video="demo.mp4",
        start_sec=2.0,
        end_sec=10.0,
        style="commentary",
        duration_band="15-25",
        hook_text=long_hook,
        output_path="out.mp4",
        burn_captions=True,
    )
    assert fg["duration_sec"] == 8.0
    assert "drawbox=x=(iw-iw*0.86)/2" in fg["vf"]
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in fg["af"]
    assert fg["command"][0] == "ffmpeg"


@pytest.mark.parametrize("detector", ["content", "adaptive", "hybrid"])
def test_detect_scenes_modes(tmp_path, detector):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from studio import synthesize_demo_video

    vid = synthesize_demo_video(tmp_path / "multi.mp4", duration_per_scene=4)
    out = detect_scenes(str(vid), str(tmp_path / f"scenes_{detector}.json"), detector=detector)
    assert out["scenes"]
    assert out["engine"] in {"pyscenedetect", "heuristic"}
    assert "cut_count" in out


def test_studio_service_and_fastapi_workflow(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    monkeypatch.setenv("CLIPOPS_STUDIO_WORKSPACE", str(tmp_path / "studio_ws"))
    monkeypatch.setenv("REMOTION_URL", "")

    from server import app  # noqa: E402

    client = TestClient(app)

    r_html = client.get("/")
    assert r_html.status_code == 200
    assert "ClipOps" in r_html.text

    r_logo = client.get("/logo.png")
    assert r_logo.status_code == 200
    assert r_logo.headers["content-type"] == "image/png"

    r_health = client.get("/api/studio/health")
    assert r_health.status_code == 200
    assert r_health.json()["engines"]["automation_boundary"] == "human_approval_manual_publish"

    # Run full demo session creation + analysis
    r_demo = client.post("/api/studio/sessions/demo", json={"auto_run": True})
    assert r_demo.status_code == 200
    sess = r_demo.json()
    sid = sess["session_id"]
    assert sess["steps"]["probe"] is True
    assert sess["steps"]["transcribe"] is True
    assert sess["steps"]["scenes"] is True
    assert sess["steps"]["score"] is True
    assert len(sess["scenes"]["scenes"]) >= 1
    assert len(sess["clips"]) >= 1

    clip_id = sess["clips"][0]["clip_id"]

    # Dry-run FFmpeg filtergraph before rendering
    r_dry = client.post(
        f"/api/studio/sessions/{sid}/clips/{clip_id}/dry-run",
        json={"style": "educational", "duration_band": "15-25"},
    )
    assert r_dry.status_code == 200
    dry = r_dry.json()
    assert dry["mode"] == "dry_run"
    assert "scale=1080:1920" in dry["ffmpeg"]["vf"]
    assert not Path(dry["target_video_path"]).exists()

    # Approve clip decision
    r_dec = client.post(
        f"/api/studio/sessions/{sid}/clips/{clip_id}/decision",
        json={"decision": "APPROVED", "notes": "Looks sharp", "style": "educational"},
    )
    assert r_dec.status_code == 200
    dec_clip = next(c for c in r_dec.json()["clips"] if c["clip_id"] == clip_id)
    assert dec_clip["decision"] == "APPROVED"

    # Execute local FFmpeg render
    r_ren = client.post(
        f"/api/studio/sessions/{sid}/clips/{clip_id}/render",
        json={"style": "educational", "duration_band": "15-25"},
    )
    assert r_ren.status_code == 200
    ren = r_ren.json()
    assert ren["ok"] is True
    assert Path(ren["video_path"]).stat().st_size > 0

    # Stream rendered media & reject traversal
    r_media = client.get(ren["video_url"])
    assert r_media.status_code == 200
    assert len(r_media.content) > 0

    r_bad = client.get(f"/api/studio/media/{sid}/../../README.md")
    assert r_bad.status_code in {400, 404}


def test_cli_health_and_dry_run():
    from cli import main as cli_main

    assert cli_main(["health"]) == 0
    assert cli_main(["dry-run", "sample.mp4", "--style", "dramatic", "--hook", "Test hook"]) == 0


def test_obsidian_vault_zero_orphans_and_valid_links():
    vault_dir = ROOT / "vault"
    notes = {p.stem: p for p in vault_dir.glob("*.md")}
    assert "Home" in notes
    assert len(notes) >= 10

    link_rx = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
    outgoing: dict[str, set[str]] = {name: set() for name in notes}
    incoming: dict[str, set[str]] = {name: set() for name in notes}

    for name, path in notes.items():
        text = path.read_text(encoding="utf-8")
        for target in link_rx.findall(text):
            target_stem = target.strip()
            assert target_stem in notes, f"Broken wikilink [[{target_stem}]] in {path.name}"
            if target_stem != name:
                outgoing[name].add(target_stem)
                incoming[target_stem].add(name)

    # Zero orphan notes: every note has >=1 incoming AND >=1 outgoing link
    for name in notes:
        assert outgoing[name], f"Note {name}.md has zero outgoing links"
        assert incoming[name], f"Orphan note {name}.md has zero incoming links"

    # Every note reachable from Home.md
    visited = {"Home"}
    q = deque(["Home"])
    while q:
        cur = q.popleft()
        for nxt in outgoing[cur]:
            if nxt not in visited:
                visited.add(nxt)
                q.append(nxt)
    assert visited == set(notes.keys()), f"Unreachable notes from Home.md: {set(notes.keys()) - visited}"

    # Verify graph.json is valid JSON
    graph_cfg = json.loads((vault_dir / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
    assert "colorGroups" in graph_cfg


def test_studio_podcast_example_and_nle_ui(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    example_mp4 = ROOT / "examples" / "sample_podcast_clip" / "source_podcast_16x9.mp4"
    if not example_mp4.exists():
        pytest.skip("sample_podcast_clip/source_podcast_16x9.mp4 not present")

    monkeypatch.setenv("CLIPOPS_STUDIO_WORKSPACE", str(tmp_path / "studio_ws_ex"))
    monkeypatch.setenv("REMOTION_URL", "")
    from server import app  # noqa: E402

    client = TestClient(app)

    r_html = client.get("/")
    assert r_html.status_code == 200
    for token in ("safezone-overlay", "wave-hook-track", "cut-span-track", "btn-example"):
        assert token in r_html.text

    r_ex = client.post("/api/studio/sessions/example", json={"auto_run": True})
    assert r_ex.status_code == 200
    sess = r_ex.json()
    assert sess["probe"]["width"] == 1280
    assert sess["probe"]["height"] == 720
    assert len(sess["probe"]["waveform"]) == 72
    assert sess["steps"]["transcribe"] is True
    assert sess["steps"]["scenes"] is True
    assert sess["steps"]["score"] is True
    assert len(sess["scenes"]["scenes"]) >= 2
    assert len(sess["clips"]) >= 1
