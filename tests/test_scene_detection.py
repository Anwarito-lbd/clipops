"""Scene detection must stay bounded.

PySceneDetect does not fail on pathological input, it just keeps going, so the
fixed-window fallback is unreachable without a wall-clock budget. One 35-minute
screen recording ran over nine hours before this was added.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.scene_detection.detect import detect_scenes


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@pytest.fixture()
def noisy_video(tmp_path: Path) -> Path:
    """Random noise — every frame differs, the worst case for ContentDetector."""
    out = tmp_path / "noise.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "nullsrc=s=640x360:d=6",
            "-f", "lavfi", "-i", "nullsrc=s=640x360:d=6",
            "-filter_complex", "[0:v]geq=random(1)*255:128:128[v]",
            "-map", "[v]", "-r", "24", "-pix_fmt", "yuv420p",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
def test_budget_exhaustion_falls_back_to_fixed_windows(noisy_video, tmp_path):
    out_json = tmp_path / "scenes.json"
    result = detect_scenes(str(noisy_video), str(out_json), time_budget_sec=0.001)

    assert result["engine"].startswith("heuristic:"), result["engine"]
    assert "budget" in result["engine"]
    assert result["scenes"], "fallback must still produce windows"
    # Windows must span the video, not stop where detection was interrupted.
    assert result["scenes"][-1]["end_sec"] > 4.0


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
def test_normal_video_completes_within_budget(noisy_video, tmp_path):
    out_json = tmp_path / "scenes.json"
    result = detect_scenes(str(noisy_video), str(out_json), time_budget_sec=120.0)

    assert result["engine"] == "pyscenedetect"
    assert json.loads(out_json.read_text())["scenes"] == result["scenes"]


def test_missing_file_falls_back_without_raising(tmp_path):
    out_json = tmp_path / "scenes.json"
    result = detect_scenes(str(tmp_path / "nope.mp4"), str(out_json))

    assert result["engine"].startswith("heuristic:")
    assert result["scenes"]
