"""PySceneDetect content & adaptive scene splitting with fixed-window fallback."""

from __future__ import annotations

import json
from pathlib import Path


def _probe_duration(video_path: str) -> float:
    duration = 60.0
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            text=True,
        )
        duration = float(out.strip())
    except Exception:
        pass
    return duration


def detect_scenes(
    video_path: str,
    output_json: str,
    *,
    detector: str = "content",
    content_threshold: float = 27.0,
    adaptive_threshold: float = 3.0,
    min_scene_len: int = 15,
) -> dict:
    """Detect scene cut boundaries using PySceneDetect ContentDetector and/or AdaptiveDetector."""
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    scenes: list[dict] = []
    engine = "heuristic"
    detector_mode = detector if detector in {"content", "adaptive", "hybrid"} else "content"

    try:
        from scenedetect import SceneManager, open_video  # type: ignore
        from scenedetect.detectors import AdaptiveDetector, ContentDetector  # type: ignore

        def _run_detector(mode: str) -> list[dict]:
            video = open_video(video_path)
            manager = SceneManager()
            if mode == "adaptive":
                manager.add_detector(
                    AdaptiveDetector(
                        adaptive_threshold=adaptive_threshold,
                        min_scene_len=min_scene_len,
                    )
                )
            else:
                manager.add_detector(
                    ContentDetector(threshold=content_threshold, min_scene_len=min_scene_len)
                )
            manager.detect_scenes(video)
            out_scenes: list[dict] = []
            for idx, (start, end) in enumerate(manager.get_scene_list()):
                s0 = round(float(start.seconds), 3)
                s1 = round(float(end.seconds), 3)
                out_scenes.append(
                    {
                        "scene_index": idx,
                        "start_sec": s0,
                        "end_sec": s1,
                        "duration_sec": round(max(0.0, s1 - s0), 3),
                        "detector": mode,
                    }
                )
            return out_scenes

        if detector_mode == "hybrid":
            scenes = _run_detector("adaptive")
            if len(scenes) <= 1:
                content_scenes = _run_detector("content")
                if len(content_scenes) >= len(scenes):
                    scenes = content_scenes
                    detector_mode = "content"
                else:
                    detector_mode = "adaptive"
            else:
                detector_mode = "adaptive"
        else:
            scenes = _run_detector(detector_mode)
        engine = "pyscenedetect"
    except Exception as exc:
        duration = _probe_duration(video_path)
        window = 8.0
        t = 0.0
        idx = 0
        while t < duration:
            s1 = round(min(t + window, duration), 3)
            scenes.append(
                {
                    "scene_index": idx,
                    "start_sec": round(t, 3),
                    "end_sec": s1,
                    "duration_sec": round(max(0.0, s1 - t), 3),
                    "detector": "fixed_window",
                }
            )
            t += window
            idx += 1
        engine = f"heuristic:{exc}"

    if not scenes:
        dur = _probe_duration(video_path)
        end_sec = round(min(15.0, dur) if dur > 0 else 15.0, 3)
        scenes = [
            {
                "scene_index": 0,
                "start_sec": 0.0,
                "end_sec": end_sec,
                "duration_sec": end_sec,
                "detector": detector_mode,
            }
        ]

    payload = {
        "scenes": scenes,
        "engine": engine,
        "detector": detector_mode,
        "cut_count": max(0, len(scenes) - 1),
    }
    Path(output_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import sys

    print(json.dumps(detect_scenes(sys.argv[1], sys.argv[2])))
