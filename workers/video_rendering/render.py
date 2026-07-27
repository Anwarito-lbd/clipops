"""FFmpeg (+ optional Auto-Editor / Remotion) account package renderer."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
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

STYLE_HOOK_COLOR = {
    "dramatic": "white",
    "educational": "white",
    "commentary": "yellow",
}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _escape_drawtext(text: str) -> str:
    # FFmpeg drawtext escaping for Windows-safe single-line hooks
    t = (text or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    t = re.sub(r"[\r\n]+", " ", t)
    return t[:90]


def _try_remotion_overlay(
    *,
    style: str,
    hook_text: str,
    caption: str,
    input_video: str,
    output_path: str,
    remotion_url: str | None,
) -> bool:
    if not remotion_url:
        return False
    try:
        req = urllib.request.Request(
            remotion_url.rstrip("/") + "/render",
            data=json.dumps(
                {
                    "style": style,
                    "hookText": hook_text,
                    "caption": caption,
                    "inputVideo": input_video,
                    "outputPath": output_path,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode() or "{}")
        # Prefer explicit rendered_path when Remotion wrote a file
        rendered = body.get("rendered_path") or body.get("outputPath")
        return bool(rendered) and Path(str(rendered)).exists() and Path(str(rendered)).stat().st_size > 0
    except Exception:
        return False


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
    remotion_url: str | None = "http://127.0.0.1:3100",
    burn_captions: bool = True,
) -> dict:
    out = Path(package_dir)
    out.mkdir(parents=True, exist_ok=True)
    video_out = out / "video.mp4"
    caption_out = out / "caption.txt"
    cover_out = out / "cover.jpg"
    base_cut = out / "base_cut.mp4"

    target = BAND_SECONDS.get(duration_band, 20.0)
    span = max(0.5, end_sec - start_sec)
    duration = min(target, span)
    zoom = STYLE_ZOOM.get(style, "1.0")
    color = STYLE_HOOK_COLOR.get(style, "white")
    hook = _escape_drawtext(hook_text or "")

    # Crop/scale to 9:16, style zoom, optional burned-in hook for first ~3s
    draw = ""
    if burn_captions and hook:
        # Style-specific placement
        if style == "educational":
            draw = (
                f",drawbox=x=40:y=ih-320:w=iw-80:h=160:color=black@0.55:t=fill,"
                f"drawtext=text='{hook}':fontcolor={color}:fontsize=42:"
                f"x=60:y=h-280:box=0"
            )
        elif style == "commentary":
            draw = (
                f",drawbox=x=(w-w*0.86)/2:y=(h-180)/2:w=w*0.86:h=160:color=black@0.65:t=fill,"
                f"drawtext=text='{hook}':fontcolor={color}:fontsize=40:"
                f"x=(w-text_w)/2:y=(h-text_h)/2"
            )
        else:  # dramatic — top hook
            draw = (
                f",drawtext=text='{hook}':fontcolor={color}:fontsize=48:"
                f"x=40:y=80:box=1:boxcolor=black@0.55:boxborderw=16"
            )

    vf = (
        f"trim=start={start_sec}:duration={duration},"
        f"setpts=PTS-STARTPTS,"
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"scale=iw*{zoom}:ih*{zoom},"
        f"crop=1080:1920"
        f"{draw}"
    )
    af = f"atrim=start={start_sec}:duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11"

    render_error = None
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
                str(base_cut),
            ]
        )
        if base_cut.exists() and base_cut.stat().st_size > 0:
            # Prefer Remotion if it actually writes a file; else use FFmpeg burn-in
            remotion_out = out / "video_remotion.mp4"
            if _try_remotion_overlay(
                style=style,
                hook_text=hook_text,
                caption=caption,
                input_video=str(base_cut),
                output_path=str(remotion_out),
                remotion_url=remotion_url,
            ):
                remotion_out.replace(video_out)
            else:
                base_cut.replace(video_out)
        else:
            raise RuntimeError("base cut empty")
    except Exception as exc:
        render_error = str(exc)
        video_out.write_bytes(b"")
        (out / "RENDER_ERROR.txt").write_text(
            f"FFmpeg render failed: {render_error}\n"
            "Ensure ffmpeg is installed and source video exists.\n",
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
        "burn_captions": burn_captions,
        "caption_engine": "ffmpeg_drawtext",
        "remotion_template": f"templates/{style}",
        "render_error": render_error,
    }
    (out / "render-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "video_path": str(video_out),
        "caption_path": str(caption_out),
        "cover_path": str(cover_out),
        "duration_sec": duration,
        "package_dir": str(out),
        "ok": video_out.exists() and video_out.stat().st_size > 0,
    }
