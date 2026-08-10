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


def _caption_filters(
    transcript_path: str, start_sec: float, end_sec: float, font: str
) -> str:
    """drawtext filters showing 2-4 spoken words at a time, timed to the speech.

    Sits at 70% height: clear of the hook at 13%, clear of the face in the middle
    band, and above the bottom fifth that TikTok's own UI covers.
    """
    import json as _json

    try:
        from workers.video_rendering.captions import group_words, words_in_window

        with open(transcript_path, encoding="utf-8") as fh:
            transcript = _json.load(fh)
        groups = group_words(words_in_window(transcript, start_sec, end_sec))
    except Exception:  # noqa: BLE001 - captions are an enhancement, never fatal
        return ""

    f_arg = f"fontfile='{_escape_fontfile(font)}':"
    parts = []
    for g in groups:
        text = _escape_drawtext(g["text"])
        if not text:
            continue
        parts.append(
            f",drawtext={f_arg}text='{text}':fontcolor=white:fontsize=58:"
            f"x=(w-text_w)/2:y=h*0.70:"
            f"box=1:boxcolor=black@0.55:boxborderw=18:"
            f"shadowcolor=black@0.9:shadowx=3:shadowy=3:"
            f"enable='between(t,{g['start']:.2f},{g['end']:.2f})'"
        )
    return "".join(parts)


def _source_dimensions(path: str) -> tuple[int, int]:
    """(width, height) of a video, or (0, 0) when ffprobe cannot read it."""
    import subprocess as _sp

    try:
        out = _sp.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
            text=True,
        ).strip()
        w, h = out.split("x")[:2]
        return int(w), int(h)
    except Exception:  # noqa: BLE001
        return 0, 0


def band_bounds(band: str | None, *, default: tuple[float, float] = (15.0, 25.0)) -> tuple[float, float]:
    """(lo, hi) seconds for a "lo-hi" band.

    A band is a range, not a target. Cutting every clip to the band's nominal
    value truncated a 24s segment the ranker had chosen - inside 15-25 - down to
    20s, which lopped the payoff off the end and made clips feel unfinished.
    """
    try:
        lo_s, _, hi_s = (band or "").partition("-")
        lo, hi = float(lo_s), float(hi_s)
    except ValueError:
        return default
    if lo <= 0 or hi < lo:
        return default
    return lo, hi

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


# drawtext resolves fonts through Fontconfig, which has no default config on
# Windows. Without an explicit fontfile it does not error - it crashes the whole
# encode with an access violation, so every clip that burns a hook on screen
# produced nothing. Naming a font file bypasses Fontconfig entirely.
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _font_file() -> str | None:
    """First usable font, or None when drawtext must be skipped."""
    import os

    override = os.environ.get("CLIPOPS_FONT_FILE")
    if override and Path(override).is_file():
        return override
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _escape_fontfile(path: str) -> str:
    """A Windows drive colon must be escaped inside a filter argument."""
    return path.replace("\\", "/").replace(":", r"\:")


# How long the hook stays on screen. Viewers decide inside the first couple of
# seconds; beyond that the text only covers the speaker.
HOOK_SECONDS = 3.0

# Hooks are kept to a single line and the font is sized to fit instead of being
# wrapped. drawtext line breaks proved unreliable to escape through the
# filtergraph parser - one backslash was unescaped to a bare "n" and welded the
# lines into "in a" + "n" + "single day", and doubling it did not help either.
# Sizing to fit removes the need for a line break at all.
_HOOK_MAX_CHARS = 52

# (max characters, font size) for a 1080-wide frame with margins, using a bold
# face at roughly 0.55 em average advance.
_HOOK_SIZES = ((22, 62), (31, 54), (38, 46), (46, 40), (_HOOK_MAX_CHARS, 34))


def _fit_hook(text: str) -> tuple[str, int]:
    """Return the hook trimmed to one line, with a font size that fits."""
    clean = " ".join((text or "").split())
    if len(clean) > _HOOK_MAX_CHARS:
        clean = clean[: _HOOK_MAX_CHARS - 1].rstrip(" ,.;:") + "…"
    for limit, size in _HOOK_SIZES:
        if len(clean) <= limit:
            return clean, size
    return clean, _HOOK_SIZES[-1][1]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _escape_drawtext(text: str) -> str:
    # FFmpeg drawtext escaping for Windows-safe single-line hooks.
    #
    # The apostrophe is substituted, not escaped. A backslash-escaped quote
    # inside a single-quoted filtergraph value closes the string early and
    # shifts the quoting of everything after it, so ffmpeg then reads a later
    # timestamp as a filter name ("No such filter: '5.04'"). Spoken captions are
    # full of contractions, and a typographic apostrophe needs no escaping and
    # looks better burned in.
    t = (text or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
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
    # Word-level timings for the spoken-word captions. Without it a clip carries
    # only the hook and then nothing for the rest of its length.
    transcript_path: str | None = None,
    # The campaign's hard duration limit. The band is a preference applied when
    # the segment was selected; cutting again at the band ceiling truncated
    # sentences the boundary snapper had deliberately extended.
    max_duration_sec: float | None = None,
) -> dict:
    out = Path(package_dir)
    out.mkdir(parents=True, exist_ok=True)
    video_out = out / "video.mp4"
    caption_out = out / "caption.txt"
    cover_out = out / "cover.jpg"
    base_cut = out / "base_cut.mp4"

    # Keep the ranker's segment whole, trimming only what the campaign forbids.
    # The segment was chosen to end on a payoff and then extended to complete the
    # sentence; re-applying the band ceiling here undid that.
    _lo, band_max = band_bounds(duration_band)
    ceiling = max_duration_sec if max_duration_sec else band_max
    span = max(0.5, end_sec - start_sec)
    duration = min(ceiling, span)
    zoom = STYLE_ZOOM.get(style, "1.0")
    color = STYLE_HOOK_COLOR.get(style, "white")
    hook = _escape_drawtext(hook_text or "")

    # Crop/scale to 9:16, style zoom, burned-in hook over the opening seconds.
    #
    # Placement is the whole game here. Centring the text vertically put a black
    # bar straight across the speaker's eyes for the full clip - it read as a
    # censor bar, not a hook. In a 9:16 crop of a talking head the face sits in
    # the middle band, so text belongs above it. The bottom is unusable too:
    # TikTok's own caption, username and buttons occupy roughly the lower fifth.
    draw = ""
    font = _font_file()
    if burn_captions and hook and font:
        f_arg = f"fontfile='{_escape_fontfile(font)}':"
        fitted, size = _fit_hook(hook_text or "")
        text = _escape_drawtext(fitted)
        # Only over the opening. Viewers decide in the first ~2s, and leaving it
        # up for twenty seconds obscures the speaker for no benefit.
        timing = f":enable='between(t,0,{HOOK_SECONDS})'"
        draw = (
            f",drawtext={f_arg}text='{text}':fontcolor={color}:fontsize={size}:"
            f"x=(w-text_w)/2:y=h*0.13:"
            f"box=1:boxcolor=black@0.6:boxborderw=24:"
            f"shadowcolor=black@0.8:shadowx=3:shadowy=3{timing}"
        )

    # Centre the 9:16 crop on the speaker rather than on the frame. Falls back
    # to the frame centre whenever the face cannot be located.
    try:
        from workers.video_rendering.reframe import crop_x_expression

        src_w, src_h = _source_dimensions(source_video)
        crop_x = crop_x_expression(source_video, start_sec, duration, src_w, src_h)
    except Exception:  # noqa: BLE001 - framing must never fail a render
        crop_x = "(in_w-1080)/2"

    # Spoken-word captions for the body of the clip. Without them the clip shows
    # a hook for three seconds and then nothing for the remaining twenty, which
    # is the clearest difference between these renders and clips that perform.
    body = ""
    if burn_captions and font and transcript_path:
        body = _caption_filters(
            transcript_path, start_sec, start_sec + duration, font
        )

    vf = (
        f"trim=start={start_sec}:duration={duration},"
        f"setpts=PTS-STARTPTS,"
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920:{crop_x}:0,"
        f"scale=iw*{zoom}:ih*{zoom},"
        f"crop=1080:1920"
        f"{body}"
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
                # loudnorm runs at 192kHz internally; without pinning the rate the
                # AAC encoder emits 96kHz, which TikTok and most players decode as
                # silence. The clip looks fine in every check and has no voice.
                "-ar",
                "48000",
                "-ac",
                "2",
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
        # Do NOT leave a zero-byte mp4 behind — a file that exists but is empty
        # reads downstream as a finished render and reaches the posting queue.
        video_out.unlink(missing_ok=True)
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
        "error": render_error,
    }
