"""PySceneDetect scene splitting with fallback."""

from __future__ import annotations

import json
from pathlib import Path


def detect_scenes(video_path: str, output_json: str) -> dict:
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    scenes: list[dict] = []
    engine = "heuristic"

    try:
        from scenedetect import SceneManager, open_video  # type: ignore
        from scenedetect.detectors import ContentDetector  # type: ignore

        video = open_video(video_path)
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=27.0))
        manager.detect_scenes(video)
        scene_list = manager.get_scene_list()
        for start, end in scene_list:
            scenes.append(
                {
                    "start_sec": start.get_seconds(),
                    "end_sec": end.get_seconds(),
                }
            )
        engine = "pyscenedetect"
    except Exception as exc:
        # Fallback: fixed windows
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
        window = 8.0
        t = 0.0
        while t < duration:
            scenes.append({"start_sec": t, "end_sec": min(t + window, duration)})
            t += window
        engine = f"heuristic:{exc}"

    if not scenes:
        scenes = [{"start_sec": 0.0, "end_sec": 15.0}]

    payload = {"scenes": scenes, "engine": engine}
    Path(output_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import sys

    print(json.dumps(detect_scenes(sys.argv[1], sys.argv[2])))
