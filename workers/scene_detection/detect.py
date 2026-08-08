"""PySceneDetect scene splitting with fallback.

Scene detection is bounded by a wall-clock budget. PySceneDetect does not fail
on pathological input - it just keeps going - so without a budget the fallback
below is unreachable. A 35-minute screen-recorded video ran for over nine hours
because ContentDetector fires on nearly every frame of a moving chart, while a
comparable talking-head video finished in 28 minutes.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

# Enough for a long talking-head source, short enough that a pathological one
# fails over to fixed windows the same day.
DEFAULT_TIME_BUDGET_SEC = 600.0


def _video_duration_sec(video_path: str) -> float | None:
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            text=True,
        )
        return float(out.strip())
    except Exception:  # noqa: BLE001
        return None


def detect_scenes(
    video_path: str,
    output_json: str,
    *,
    time_budget_sec: float = DEFAULT_TIME_BUDGET_SEC,
    frame_skip: int = 2,
) -> dict:
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    scenes: list[dict] = []
    engine = "heuristic"

    try:
        from scenedetect import SceneManager, open_video  # type: ignore
        from scenedetect.detectors import ContentDetector  # type: ignore

        video = open_video(video_path)
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=27.0))

        timed_out = threading.Event()

        def _stop() -> None:
            timed_out.set()
            manager.stop()

        watchdog = threading.Timer(time_budget_sec, _stop)
        watchdog.daemon = True
        watchdog.start()
        try:
            manager.detect_scenes(video, frame_skip=frame_skip)
        finally:
            watchdog.cancel()

        if timed_out.is_set():
            # Partial results cover only the head of the video, which would
            # silently confine every clip to the opening minutes.
            raise TimeoutError(
                f"scene detection exceeded {time_budget_sec:.0f}s budget"
            )

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
        duration = _video_duration_sec(video_path) or 60.0
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
