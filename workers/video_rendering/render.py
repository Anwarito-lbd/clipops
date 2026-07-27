"""FFmpeg (+ optional Auto-Editor) account package renderer."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


BAND_SECONDS = {
    "15-25": 20.0,
    "25-40": 32.0,
    "40-60": 48.0,
}

STYLE_ZOOM = {
    "dramatic": "1.12",
    "educational": "1.00",
    "commentary": "1.06",
}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def render_account_package(
    *,
    source_video: str,
    start_sec: float,
    end_sec: float,
    style: str,
    duration_band: str,
    caption: str,
    hook_text: str,
    package_dir: str,
    ffmpeg_path: str = "ffmpeg",
    auto_editor: bool = False,
) -> dict:
    out = Path(package_dir)
    out.mkdir(parents=True, exist_ok=True)
    video_out = out / "video.mp4"
    caption_out = out / "caption.txt"
    cover_out = out / "cover.jpg"

    target = BAND_SECONDS.get(duration_band, 20.0)
    span = max(0.5, end_sec - start_sec)
    duration = min(target, span)
    zoom = STYLE_ZOOM.get(style, "1.0")

    # Crop/scale to 9:16, light zoom per style, loudnorm
    vf = (
        f"trim=start={start_sec}:duration={duration},"
        f"setpts=PTS-STARTPTS,"
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"scale=iw*{zoom}:ih*{zoom},"
        f"crop=1080:1920"
    )
    af = f"atrim=start={start_sec}:duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11"

    try:
        _run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                source_video,
                "-vf",
                vf,
                "-af",
                af,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(video_out),
            ]
        )
    except Exception:
        # If ffmpeg filters fail (e.g. missing file), write a placeholder note package
        video_out.write_bytes(b"")
        (out / "RENDER_ERROR.txt").write_text(
            "FFmpeg render failed — ensure ffmpeg is installed and source video exists.\n"
            "Remotion overlays can be applied via templates/{style} once base cut exists.\n",
            encoding="utf-8",
        )

    if auto_editor and video_out.exists() and video_out.stat().st_size > 0:
        try:
            edited = out / "video_ae.mp4"
            _run(["auto-editor", str(video_out), "--output", str(edited)])
            if edited.exists():
                edited.replace(video_out)
        except Exception:
            pass

    # Cover frame
    try:
        _run(
            [
                ffmpeg_path,
                "-y",
                "-ss",
                str(start_sec + min(1.0, duration / 3)),
                "-i",
                source_video,
                "-frames:v",
                "1",
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                str(cover_out),
            ]
        )
    except Exception:
        cover_out.write_bytes(b"")

    caption_out.write_text(caption, encoding="utf-8")
    meta = {
        "style": style,
        "duration_band": duration_band,
        "hook_text": hook_text,
        "duration_sec": duration,
        "remotion_template": f"templates/{style}",
        "note": "Base cut via FFmpeg; animated captions via Remotion template service",
    }
    (out / "render-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "video_path": str(video_out),
        "caption_path": str(caption_out),
        "cover_path": str(cover_out),
        "duration_sec": duration,
        "package_dir": str(out),
    }
