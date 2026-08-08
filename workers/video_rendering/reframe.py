"""Face-tracked horizontal crop for the 9:16 reframe.

The renderer previously did `crop=1080:1920` with no x offset - a dead-centre
crop. On a 1920x1080 talking head where the speaker sits off-centre that clips
part of the face, which is the single most visible way a clip looks amateur.

Crop maths follows vendor/claude-shorts/compute_reframe.py. Detection is the
mediapipe Tasks API rather than that file's `mp.solutions` calls: the legacy
solutions module is absent from every currently installable mediapipe build,
so the vendored function cannot run as written.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

MODEL = Path(__file__).resolve().parents[2] / "vendor" / "models" / "blaze_face_short_range.tflite"

# Below this, detections are too sparse to trust and centre is the safer crop.
MIN_SAMPLES = 2


def _sample_face_centres(
    video_path: str, start_sec: float, duration: float, samples: int = 6
) -> list[float]:
    """Normalised face x-centres (0-1) sampled across the clip window."""
    if not MODEL.is_file():
        return []
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions
    except Exception:  # noqa: BLE001 - detection is optional, never fail a render
        return []

    detector = FaceDetector.create_from_options(
        FaceDetectorOptions(base_options=BaseOptions(model_asset_path=str(MODEL)))
    )
    centres: list[float] = []
    tmpdir = tempfile.mkdtemp()
    try:
        for i in range(samples):
            ts = start_sec + duration * (i + 0.5) / samples
            frame = os.path.join(tmpdir, f"f{i}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                 "-vframes", "1", "-q:v", "2", frame],
                capture_output=True,
            )
            if not os.path.exists(frame):
                continue
            img = cv2.imread(frame)
            os.unlink(frame)
            if img is None:
                continue
            h, w = img.shape[:2]
            mp_img = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
            )
            result = detector.detect(mp_img)
            if not result.detections:
                continue
            best = max(
                result.detections,
                key=lambda d: d.bounding_box.width * d.bounding_box.height,
            )
            bb = best.bounding_box
            centres.append((bb.origin_x + bb.width / 2) / w)
    finally:
        detector.close()
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
    return centres


def crop_x_expression(
    video_path: str,
    start_sec: float,
    duration: float,
    src_w: int,
    src_h: int,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
) -> str:
    """FFmpeg crop x offset (in scaled-frame pixels) centred on the speaker.

    Returns "(in_w-out_w)/2" - the previous centre behaviour - whenever the face
    cannot be located, so a detection failure degrades to what it did before
    rather than to a wrong crop.
    """
    centre_expr = f"(in_w-{out_w})/2"
    if not src_w or not src_h:
        return centre_expr

    centres = _sample_face_centres(video_path, start_sec, duration)
    if len(centres) < MIN_SAMPLES:
        return centre_expr

    centres.sort()
    median = centres[len(centres) // 2]

    # Frame width after scale=…:force_original_aspect_ratio=increase.
    scaled_w = max(out_w, int(round(src_w * (out_h / src_h))))
    face_x = median * scaled_w
    x = int(round(face_x - out_w / 2))
    x = max(0, min(x, scaled_w - out_w))
    return str(x)
