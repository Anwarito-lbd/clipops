"""Cut a window from recorded segments, burn Whisper captions, render 9:16.

"FFmpeg cuts 30 seconds" -> "Whisper adds captions" -> "Your clip's ready".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .recorder import Segment

# -- cutting ----------------------------------------------------------------


def select_segments(segments: list[Segment], start: float, end: float) -> list[Segment]:
    return [s for s in segments if s.end > start and s.start < end]


def segment_input(segments: list[Segment], start: float, end: float) -> tuple[str, float]:
    """FFmpeg input + seek offset covering [start, end) across recorded TS segments."""
    chosen = select_segments(segments, start, end)
    if not chosen:
        raise ValueError(f"no recorded segments cover {start:.1f}-{end:.1f}s")
    missing = [str(s.path) for s in chosen if not s.path.exists()]
    if missing:
        raise FileNotFoundError(f"segments pruned or missing: {missing[:3]}")
    if len(chosen) == 1:
        src = str(chosen[0].path.resolve())
    else:
        # MPEG-TS can be byte-concatenated; the concat protocol reads them as one stream.
        src = "concat:" + "|".join(str(s.path.resolve()) for s in chosen)
    return src, max(0.0, start - chosen[0].start)


def cut_window(
    segments: list[Segment], start: float, end: float, out_path: str | Path, *, ffmpeg: str = "ffmpeg"
) -> dict:
    """Frame-accurate re-encoded cut of [start, end) (recording seconds) across TS segments."""
    src, offset = segment_input(segments, start, end)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{offset:.3f}", "-i", src, "-t", f"{end - start:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    n = len(select_segments(segments, start, end))
    return {"path": str(out_path), "start": start, "end": end, "segments": n}


# -- captions ---------------------------------------------------------------


def chunk_words(
    words: list[dict], *, max_words: int = 3, max_chars: int = 18, max_gap: float = 0.6
) -> list[tuple[float, float, str]]:
    """Group word timestamps into short punchy caption chunks ("HE DID NOT")."""
    chunks: list[tuple[float, float, str]] = []
    cur: list[dict] = []

    def text_of(ws: list[dict]) -> str:
        return "".join(w["word"] for w in ws).strip()

    def emit() -> None:
        if cur:
            chunks.append((float(cur[0]["start"]), float(cur[-1]["end"]), text_of(cur)))

    for w in words:
        raw = w.get("word") or ""
        token = raw.strip()
        if not token or w.get("start") is None or w.get("end") is None:
            continue
        # Whisper marks a new word with a leading space; tokens without one ("%", "'s", "-ish")
        # continue the previous word and must never start a new caption chunk.
        continues = bool(cur) and not raw[:1].isspace() and not token[:1].isalnum()
        piece = {"word": (raw if raw[:1].isspace() else " " + token) if not continues else token,
                 "start": float(w["start"]), "end": float(w["end"])}
        if continues:
            cur[-1] = {**cur[-1], "word": cur[-1]["word"] + piece["word"], "end": piece["end"]}
            continue
        gap = piece["start"] - cur[-1]["end"] if cur else 0.0
        if cur and (len(cur) >= max_words or len(text_of(cur + [piece])) > max_chars or gap > max_gap):
            emit()
            cur = []
        cur.append(piece)
        if token[-1:] in ".?!":
            emit()
            cur = []
    emit()
    # Hold each chunk until the next one starts (no flicker), capped at +0.8 s.
    held = []
    for i, (s, e, t) in enumerate(chunks):
        nxt = chunks[i + 1][0] if i + 1 < len(chunks) else e + 0.8
        held.append((s, max(e, min(nxt, e + 0.8)), t))
    return held


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(
    chunks: list[tuple[float, float, str]],
    *,
    width: int = 1080,
    height: int = 1920,
    font: str = "DejaVu Sans",
    font_size: int = 92,
    margin_v: int = 640,
    uppercase: bool = True,
) -> str:
    """Bold white uppercase captions, thick black outline, quick pop-in — the stream-clip look."""
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Clip,{font},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,7,3,2,60,60,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    pop = r"{\fscx70\fscy70\t(0,90,\fscx108\fscy108)\t(90,160,\fscx100\fscy100)}"
    lines = []
    for s, e, text in chunks:
        t = _ass_escape(text.upper() if uppercase else text)
        lines.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Clip,,0,0,0,,{pop}{t}")
    return header + "\n".join(lines) + "\n"


# -- vertical render ----------------------------------------------------------


# Caption baseline (ASS MarginV, px from bottom) that suits each layout.
CAPTION_MARGIN = {"blur": 500, "crop": 640, "split": 1190}


def vertical_filter(
    layout: str = "blur",
    *,
    subtitles: str | None = None,
    facecam: tuple[float, float, float, float] | None = None,
    cam_height: int = 640,
) -> str:
    """9:16 filtergraph.

    blur  — whole 16:9 frame centred over a blurred fill (safe default for any stream)
    crop  — centre crop to fill the screen
    split — streamer facecam on top, gameplay below (the classic stream-clip look);
            `facecam` is the cam rectangle as fractions of the source (x, y, w, h)
    """
    if layout == "crop":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    elif layout == "split":
        fx, fy, fw, fh = facecam or (0.0, 0.0, 0.25, 0.25)
        game_h = 1920 - cam_height
        vf = (
            "split=2[cam][game];"
            f"[cam]crop=iw*{fw}:ih*{fh}:iw*{fx}:ih*{fy},"
            f"scale=1080:{cam_height}:force_original_aspect_ratio=increase,crop=1080:{cam_height}[c];"
            f"[game]scale=-2:{game_h},crop=1080:{game_h}[g];"
            "[c][g]vstack=inputs=2,setsar=1"
        )
    else:
        vf = (
            "split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.08[bgb];"
            "[fg]scale=1080:-2:force_original_aspect_ratio=decrease[fgs];"
            "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    if subtitles:
        vf += f",subtitles=filename={subtitles}"
    return vf


def render_vertical(
    clip_path: str | Path,
    out_path: str | Path,
    *,
    ass_path: str | Path | None = None,
    layout: str = "blur",
    facecam: tuple[float, float, float, float] | None = None,
    preset: str = "fast",
    loudnorm: bool = True,
    seek: tuple[float, float] | None = None,
    ffmpeg: str = "ffmpeg",
) -> dict:
    """Render a 9:16 clip. `clip_path` may be a file or a `concat:` segment source with `seek=(offset, duration)`."""
    out_path = Path(out_path)
    workdir = out_path.parent
    # Run from the clip folder with a bare .ass filename: avoids filter-path escaping on every OS.
    sub = None
    if ass_path:
        ass_path = Path(ass_path)
        if ass_path.parent.resolve() != workdir.resolve():
            (workdir / ass_path.name).write_text(ass_path.read_text(encoding="utf-8"), encoding="utf-8")
        sub = ass_path.name
    vf = vertical_filter(layout, subtitles=sub, facecam=facecam)
    audio = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] if loudnorm else []
    src = str(clip_path) if str(clip_path).startswith("concat:") else str(Path(clip_path).resolve())
    inp = ["-ss", f"{seek[0]:.3f}", "-i", src, "-t", f"{seek[1]:.3f}"] if seek else ["-i", src]
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inp,
        "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", preset, "-crf", "20", "-r", "30",
        *audio, "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", out_path.name,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=str(workdir))
    return {"path": str(out_path), "layout": layout, "preset": preset, "filter": vf}


def extract_thumbnail(video: str | Path, out_jpg: str | Path, *, at: float = 1.0, ffmpeg: str = "ffmpeg") -> None:
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(at), "-i", str(video),
         "-frames:v", "1", "-q:v", "3", str(out_jpg)],
        check=True, capture_output=True,
    )
