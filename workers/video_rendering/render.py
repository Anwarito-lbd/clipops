"""FFmpeg (+ optional Auto-Editor / Remotion) short-form package renderer."""

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
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

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _resolve_fontfile() -> str | None:
    """Return an existing system font path so FFmpeg drawtext works without Fontconfig."""
    override = os.environ.get("CLIPOPS_FONTFILE")
    if override and Path(override).exists():
        return override
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _escape_drawtext(text: str) -> str:
    # FFmpeg drawtext escaping for Windows-safe lines
    t = (text or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    t = re.sub(r"[\r\n]+", " ", t)
    return t[:120]


def _wrap_drawtext_lines(text: str, *, max_chars: int = 26, max_lines: int = 3) -> list[str]:
    """Wrap hook text into short balanced lines that always fit inside a 1080px portrait frame."""
    cleaned = re.sub(r"[\r\n]+", " ", (text or "").strip())
    if not cleaned:
        return []
    lines = textwrap.wrap(cleaned, width=max_chars, break_long_words=True, break_on_hyphens=True)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if len(lines[-1]) > max_chars - 3:
            lines[-1] = lines[-1][: max_chars - 3].rstrip() + "..."
        else:
            lines[-1] = lines[-1].rstrip() + "..."
    return [_escape_drawtext(line) for line in lines if line.strip()]


def build_filtergraph(
    *,
    source_video: str,
    start_sec: float,
    end_sec: float,
    style: str,
    duration_band: str,
    hook_text: str,
    output_path: str,
    ffmpeg_path: str = "ffmpeg",
    burn_captions: bool = True,
) -> dict:
    """Build deterministic FFmpeg video/audio filtergraphs and CLI args for preview or execution."""
    target = BAND_SECONDS.get(duration_band, 20.0)
    span = max(0.5, float(end_sec) - float(start_sec))
    duration = min(target, span)
    zoom = STYLE_ZOOM.get(style, "1.0")
    color = STYLE_HOOK_COLOR.get(style, "white")
    wrapped_lines = _wrap_drawtext_lines(hook_text or "", max_chars=26, max_lines=3)
    fontfile = _resolve_fontfile()
    font_opt = f"fontfile='{_escape_filter_path(fontfile)}':" if fontfile else ""

    draw = ""
    if burn_captions and wrapped_lines:
        if style == "educational":
            box_h = 44 + len(wrapped_lines) * 46
            offset_bottom = box_h + 150
            line_filters = ",".join(
                f"drawtext={font_opt}text='{line}':fontcolor={color}:fontsize=36:"
                f"x=(w-text_w)/2:y=h-{offset_bottom - (24 + idx * 46)}"
                for idx, line in enumerate(wrapped_lines)
            )
            draw = (
                f",drawbox=x=56:y=ih-{offset_bottom}:w=iw-112:h={box_h}:color=black@0.65:t=fill,"
                f"{line_filters}"
            )
        elif style == "commentary":
            # drawbox's own w/h are the box size, so frame size must be iw/ih.
            line_h = 44
            start_offset = -((len(wrapped_lines) - 1) * line_h) // 2
            line_filters = ",".join(
                f"drawtext={font_opt}text='{line}':fontcolor={color}:fontsize=36:"
                f"x=(w-text_w)/2:y=(h-text_h)/2+({start_offset + idx * line_h})"
                for idx, line in enumerate(wrapped_lines)
            )
            draw = (
                f",drawbox=x=(iw-iw*0.86)/2:y=(ih-180)/2:w=iw*0.86:h=160:color=black@0.68:t=fill,"
                f"{line_filters}"
            )
        else:  # dramatic — top hook safely wrapped inside 1080px portrait margins
            box_h = 42 + len(wrapped_lines) * 48
            line_filters = ",".join(
                f"drawtext={font_opt}text='{line}':fontcolor={color}:fontsize=38:"
                f"x=(w-text_w)/2:y={98 + idx * 48}"
                for idx, line in enumerate(wrapped_lines)
            )
            draw = (
                f",drawbox=x=56:y=78:w=iw-112:h={box_h}:color=black@0.68:t=fill,"
                f"{line_filters}"
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
    command = [
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
        output_path,
    ]
    return {
        "style": style,
        "duration_band": duration_band,
        "duration_sec": round(duration, 3),
        "zoom": zoom,
        "fontfile": fontfile,
        "vf": vf,
        "af": af,
        "command": command,
    }


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

    plan = build_filtergraph(
        source_video=source_video,
        start_sec=start_sec,
        end_sec=end_sec,
        style=style,
        duration_band=duration_band,
        hook_text=hook_text,
        output_path=str(base_cut),
        ffmpeg_path=ffmpeg_path,
        burn_captions=burn_captions,
    )
    duration = plan["duration_sec"]

    render_error = None
    try:
        _run(plan["command"])
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
