"""FFmpeg (+ optional Auto-Editor / Remotion / Edge-TTS) account package renderer."""

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


def _strong_hook_draw(*, style: str, hook: str, color: str) -> str:
    """MoneyPrinterTurbo-inspired thicker outline / box burn-in (FFmpeg fallback)."""
    if not hook:
        return ""
    if style == "educational":
        return (
            f",drawbox=x=32:y=ih-360:w=iw-64:h=200:color=black@0.72:t=fill,"
            f"drawbox=x=32:y=ih-360:w=8:h=200:color=0x3dd6c6@1:t=fill,"
            f"drawtext=text='{hook}':fontcolor={color}:fontsize=44:"
            f"x=56:y=h-300:borderw=3:bordercolor=black@0.85"
        )
    if style == "commentary":
        return (
            f",drawbox=x=(w-w*0.9)/2:y=(h-200)/2:w=w*0.9:h=190:color=black@0.78:t=fill,"
            f"drawbox=x=(w-w*0.9)/2:y=(h-200)/2:w=w*0.9:h=190:color=yellow@0.9:t=4,"
            f"drawtext=text='{hook}':fontcolor=yellow:fontsize=42:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=4:bordercolor=black@0.9"
        )
    # dramatic — big top hook with outline
    return (
        f",drawtext=text='{hook}':fontcolor={color}:fontsize=52:"
        f"x=40:y=72:box=1:boxcolor=black@0.6:boxborderw=18:"
        f"borderw=4:bordercolor=black@0.9"
    )


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
    enable_tts_commentary: bool = False,
    tts_voice: str = "en-US-JennyNeural",
    campaign_name: str = "",
    excerpt: str = "",
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
        draw = _strong_hook_draw(style=style, hook=hook, color=color)

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
    tts_meta: dict = {}
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

            # Optional TTS commentary on campaign footage (commentary style only)
            from workers.video_rendering.tts_commentary import maybe_apply_tts_commentary

            tts_meta = maybe_apply_tts_commentary(
                style=style,
                enabled=enable_tts_commentary,
                video_path=video_out,
                hook_text=hook_text,
                excerpt=excerpt,
                campaign_name=campaign_name,
                package_dir=out,
                ffmpeg_path=ffmpeg_path,
                voice=tts_voice,
            )
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
        "caption_engine": "remotion_karaoke_or_ffmpeg_drawtext",
        "subtitle_style": "strong_outline_karaoke",
        "remotion_template": f"templates/{style}",
        "tts_commentary": tts_meta,
        "render_error": render_error,
        "footage_source": "campaign_asset",
        "note": "Not MoneyPrinterTurbo stock+TTS rewrite — campaign footage only",
    }
    (out / "render-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "video_path": str(video_out),
        "caption_path": str(caption_out),
        "cover_path": str(cover_out),
        "duration_sec": duration,
        "package_dir": str(out),
        "ok": video_out.exists() and video_out.stat().st_size > 0,
        "tts_commentary": tts_meta,
    }
