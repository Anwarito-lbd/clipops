"""Speaker-tracked vertical reframe via the vendored openshorts engine.

Our own reframe computes one crop offset for the whole clip. openshorts drives a
per-frame crop through ffmpeg `sendcmd`, so the camera follows the speaker, and
its punch_in module pushes in on emphasis beats. Its own note on why that
matters:

    "A static crop for 45 seconds is the single most 'unedited' thing a vertical
    clip can do."

Only the reframe path is used. openshorts' clip selection routes through Gemini,
which is out of quota on this account, and our ranker is free, faster, and
reproduces the benchmark batch - so selection stays where it is.

The vendored package uses top-level imports and expects to run from its own
directory, so it is invoked in a subprocess rather than imported into the API
process, which also keeps its heavy torch/ultralytics import out of ours.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OPENSHORTS = Path(__file__).resolve().parents[2] / "vendor" / "openshorts"

# openshorts' punch-in is opt-in via env var. Emphasis-timed push is the pacing
# the clips were missing, so it is on for our renders.
_ENV = {"PUNCH_IN": "1"}

_DRIVER = """
import json, os, sys
sys.path.insert(0, os.getcwd())
import reframe_v2
src, dst = sys.argv[1], sys.argv[2]
# openshorts takes the ratio as a float (main.ASPECT_RATIO = 9/16), not "9:16":
# a string here gets multiplied by the height and repeated.
aspect = float(sys.argv[3])
try:
    reframe_v2.render(src, dst, aspect)
    print("OPENSHORTS_OK")
except Exception as exc:
    print("OPENSHORTS_FAIL " + type(exc).__name__ + ": " + str(exc)[:300])
    sys.exit(1)
"""


def available() -> bool:
    return (OPENSHORTS / "reframe_v2.py").is_file()


def reframe(
    input_video: str,
    output_video: str,
    *,
    aspect_ratio: float = 9 / 16,
    timeout: float = 900.0,
) -> tuple[bool, str]:
    """Speaker-tracked vertical reframe. Returns (ok, detail).

    Never raises: a reframe failure must fall back to the static crop rather
    than fail the render.
    """
    if not available():
        return False, "openshorts not vendored"

    import os

    env = {**os.environ, **_ENV}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DRIVER, input_video, output_video, str(aspect_ratio)],
            cwd=str(OPENSHORTS),
            env=env,
            capture_output=True,
            text=True,
            # openshorts logs emoji; the Windows default (cp1252) raises
            # UnicodeDecodeError while reading the pipe and the render looks
            # like it failed when it did not.
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout:.0f}s"

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "OPENSHORTS_OK" not in out:
        detail = next(
            (ln for ln in out.splitlines() if ln.startswith("OPENSHORTS_FAIL")),
            f"exit {proc.returncode}",
        )
        return False, detail[:300]

    dest = Path(output_video)
    if not dest.is_file() or dest.stat().st_size == 0:
        return False, "produced no file"
    return True, "ok"
