"""Generate a realistic 3-scene 16:9 spoken podcast example and run ClipOps end-to-end.

Uses Windows System.Speech TTS voices (David + Zira) and FFmpeg to synthesize a
three-scene 1280x720 talk-track video with real spoken English dialogue, then
runs the actual ClipOps pipeline:
  1. faster-whisper ASR + word-level alignment (CPU int8)
  2. PySceneDetect hybrid shot-boundary detection
  3. ClipRankingService hook/retention scoring
  4. FFmpeg 16:9 -> 9:16 (1080x1920) vertical render + before/after frame strip & GIF

Outputs:
  - examples/sample_podcast_clip/source_podcast_16x9.mp4
  - examples/sample_podcast_clip/README.md
  - docs/proof/example-rendered-clip.mp4
  - docs/proof/example-frame-strip.png
  - docs/proof/example-rendered-preview.gif
  - docs/proof/example-podcast-summary.json
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.services.clip_ranking import ClipRankingService  # noqa: E402
from workers.caption_generation.generate import generate_account_copy  # noqa: E402
from workers.scene_detection.detect import detect_scenes  # noqa: E402
from workers.transcription.transcribe import transcribe_video  # noqa: E402
from workers.video_rendering.render import render_account_package  # noqa: E402


@dataclass(frozen=True)
class SceneSpec:
    index: int
    speaker: str
    voice: str
    chapter: str
    bg_color: str
    accent_color: str
    keyframe_name: str
    card_title: str
    card_subtitle: str
    spoken_text: str


SCENES: list[SceneSpec] = [
    SceneSpec(
        index=1,
        speaker="HOST // DAVID",
        voice="Microsoft David Desktop",
        chapter="01 // SETUP",
        bg_color="0x0e2239",
        accent_color="0x38bdf8",
        keyframe_name="scene1_host.png",
        card_title="WHY PODCASTS DROP",
        card_subtitle="Retention Dropoff Audit",
        spoken_text=(
            "Most creators spend three hours recording a great episode, "
            "and then they lose eighty percent of viewers in the first two seconds "
            "because nobody frames the tension upfront."
        ),
    ),
    SceneSpec(
        index=2,
        speaker="GUEST // ZIRA",
        voice="Microsoft Zira Desktop",
        chapter="02 // REFRAME",
        bg_color="0x3b1847",
        accent_color="0xf59e0b",
        keyframe_name="scene2_guest.png",
        card_title="LEAD WITH THE CLAIM",
        card_subtitle="3-Second Hook Rule",
        spoken_text=(
            "Wait, here is the secret nobody talks about! "
            "Instead of starting with polite introductions, open right on the sharpest claim, "
            "cut dead air every four seconds, and verify every caption before you export."
        ),
    ),
    SceneSpec(
        index=3,
        speaker="STUDIO // WORKFLOW",
        voice="Microsoft David Desktop",
        chapter="03 // WORKFLOW",
        bg_color="0x0e382b",
        accent_color="0x10b981",
        keyframe_name="scene3_studio.png",
        card_title="HUMAN GATE EXPORT",
        card_subtitle="WhisperX + PySceneDetect",
        spoken_text=(
            "That is the exact ClipOps workflow: word-level timestamps, "
            "clean scene boundaries, and one human approval gate before the vertical render."
        ),
    ),
]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def _synthesize_wav(text: str, voice_name: str, out_wav: Path, rate: int = 1) -> float:
    """Synthesize spoken English WAV via Windows System.Speech."""
    escaped_text = text.replace("'", "''")
    escaped_voice = voice_name.replace("'", "''")
    escaped_path = str(out_wav).replace("'", "''")
    ps_script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"try {{ $s.SelectVoice('{escaped_voice}') }} catch {{}}; "
        f"$s.Rate = {rate}; "
        f"$s.SetOutputToWaveFile('{escaped_path}'); "
        f"$s.Speak('{escaped_text}'); "
        "$s.Dispose();"
    )
    _run(["powershell", "-NoProfile", "-Command", ps_script])
    with wave.open(str(out_wav), "rb") as wf:
        frames = wf.getnframes()
        framerate = wf.getframerate()
        return frames / float(framerate)


def _escape_drawtext(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _ffprobe_duration(path: Path) -> float:
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(proc.stdout.strip())


def _build_scene_mp4(scene: SceneSpec, wav_path: Path, duration: float, out_mp4: Path) -> None:
    """Render one 1280x720 scene from studio keyframe (with subtle motion + clean lower-third) and speaker audio."""
    fontfile = "C\\:/Windows/Fonts/arial.ttf"
    padded_dur = round(duration + 0.35, 3)
    keyframe = REPO_ROOT / "examples" / "sample_podcast_clip" / scene.keyframe_name

    # Keep lower-third inside the center 404px (9:16 crop safe column) at bottom of 720p frame
    # so the speaker's face remains unobstructed and zero text clips when cropped to 1080x1920.
    filters = [
        f"scale=1320:742,crop=1280:720:x='(iw-1280)/2':y='(ih-720)/2'",
        f"drawbox=x=438:y=598:w=404:h=98:color=0x060a12@0.82:t=fill",
        f"drawbox=x=438:y=598:w=404:h=3:color={scene.accent_color}@0.95:t=fill",
        (
            f"drawtext=fontfile='{fontfile}':text='{_escape_drawtext(scene.chapter + '  |  ' + scene.speaker)}':"
            f"fontsize=15:fontcolor={scene.accent_color}:x=(w-text_w)/2:y=612"
        ),
        (
            f"drawtext=fontfile='{fontfile}':text='{_escape_drawtext(scene.card_title)}':"
            "fontsize=23:fontcolor=0xf8fafc:x=(w-text_w)/2:y=638"
        ),
        (
            f"drawtext=fontfile='{fontfile}':text='{_escape_drawtext(scene.card_subtitle)}':"
            "fontsize=15:fontcolor=0x94a3b8:x=(w-text_w)/2:y=668"
        ),
    ]
    vf = ",".join(filters)
    if keyframe.exists():
        video_input = ["-loop", "1", "-t", str(padded_dur), "-i", str(keyframe)]
    else:
        video_input = ["-f", "lavfi", "-i", f"color=c={scene.bg_color}:s=1280x720:r=30:d={padded_dur}"]

    _run(
        [
            "ffmpeg",
            "-y",
            *video_input,
            "-i",
            str(wav_path),
            "-r",
            "30",
            "-vf",
            vf,
            "-af",
            f"apad=pad_dur=0.35,atrim=0:{padded_dur}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "96k",
            "-shortest",
            str(out_mp4),
        ]
    )


def _build_frame_strip(source_video: Path, rendered_clip: Path, out_png: Path) -> None:
    """Create a crisp before (16:9) -> after (9:16) visual comparison contact sheet."""
    tmp_dir = out_png.parent / "_strip_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        src_dur = _ffprobe_duration(source_video)
        ren_dur = _ffprobe_duration(rendered_clip)
        src_times = [round(src_dur * p, 2) for p in (0.14, 0.52, 0.85)]
        ren_times = [round(ren_dur * p, 2) for p in (0.15, 0.50, 0.85)]

        src_imgs: list[Path] = []
        ren_imgs: list[Path] = []
        for idx, ts in enumerate(src_times):
            p = tmp_dir / f"src_{idx}.png"
            _run(["ffmpeg", "-y", "-ss", str(ts), "-i", str(source_video), "-vframes", "1", str(p)])
            src_imgs.append(p)
        for idx, ts in enumerate(ren_times):
            p = tmp_dir / f"ren_{idx}.png"
            _run(["ffmpeg", "-y", "-ss", str(ts), "-i", str(rendered_clip), "-vframes", "1", str(p)])
            ren_imgs.append(p)

        canvas = Image.new("RGB", (1320, 760), (9, 13, 20))
        draw = ImageDraw.Draw(canvas)
        try:
            font_lg = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
            font_sm = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
        except OSError:
            font_lg = ImageFont.load_default()
            font_sm = ImageFont.load_default()

        draw.text((36, 22), "BEFORE: 16:9 Source Podcast (1280x720, 3 Spoken Scenes)", fill=(56, 189, 248), font=font_lg)
        for idx, img_path in enumerate(src_imgs):
            im = Image.open(img_path).resize((392, 220), Image.Resampling.LANCZOS)
            x = 36 + idx * 424
            y = 62
            canvas.paste(im, (x, y))
            draw.rectangle([x, y, x + 392, y + 220], outline=(51, 65, 85), width=2)
            draw.text((x, y + 228), f"Scene {idx + 1} @ t={src_times[idx]}s", fill=(148, 163, 184), font=font_sm)

        draw.text(
            (36, 336),
            "AFTER: Rendered 9:16 Vertical Short (1080x1920, Center Crop + Hook Overlay + Safe Captions)",
            fill=(16, 185, 129),
            font=font_lg,
        )
        for idx, img_path in enumerate(ren_imgs):
            im = Image.open(img_path).resize((198, 352), Image.Resampling.LANCZOS)
            x = 132 + idx * 424
            y = 376
            canvas.paste(im, (x, y))
            draw.rectangle([x, y, x + 198, y + 352], outline=(16, 185, 129), width=2)
            draw.text((x, y + 358), f"Short frame @ t={ren_times[idx]}s", fill=(148, 163, 184), font=font_sm)

        canvas.save(out_png, optimize=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _build_gif_preview(rendered_clip: Path, out_gif: Path) -> None:
    """Create a lightweight animated GIF preview of the 9:16 rendered output."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(rendered_clip),
            "-vf",
            "fps=10,scale=324:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse",
            str(out_gif),
        ]
    )


def main() -> None:
    example_dir = REPO_ROOT / "examples" / "sample_podcast_clip"
    proof_dir = REPO_ROOT / "docs" / "proof"
    example_dir.mkdir(parents=True, exist_ok=True)
    proof_dir.mkdir(parents=True, exist_ok=True)

    source_video = example_dir / "source_podcast_16x9.mp4"
    rendered_clip = proof_dir / "example-rendered-clip.mp4"
    frame_strip = proof_dir / "example-frame-strip.png"
    rendered_gif = proof_dir / "example-rendered-preview.gif"
    summary_json = proof_dir / "example-podcast-summary.json"

    with tempfile.TemporaryDirectory(prefix="clipops_podcast_") as tmp_str:
        tmp_dir = Path(tmp_str)
        scene_mp4s: list[Path] = []
        scene_durations: list[dict[str, object]] = []

        for scene in SCENES:
            wav_path = tmp_dir / f"scene_{scene.index}.wav"
            mp4_path = tmp_dir / f"scene_{scene.index}.mp4"
            dur = _synthesize_wav(scene.spoken_text, scene.voice, wav_path, rate=1)
            _build_scene_mp4(scene, wav_path, dur, mp4_path)
            actual_dur = _ffprobe_duration(mp4_path)
            scene_mp4s.append(mp4_path)
            scene_durations.append(
                {
                    "scene": scene.index,
                    "speaker": scene.speaker,
                    "voice": scene.voice,
                    "chapter": scene.chapter,
                    "duration_sec": round(actual_dur, 3),
                    "script": scene.spoken_text,
                }
            )

        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in scene_mp4s),
            encoding="utf-8",
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                str(source_video),
            ]
        )

        transcript_json = tmp_dir / "transcript.json"
        scenes_json = tmp_dir / "scenes.json"

        print("[1/4] Running faster-whisper transcription (CPU int8)...")
        transcript = transcribe_video(
            str(source_video),
            str(transcript_json),
            model="tiny",
            device="cpu",
            compute_type="int8",
            enable_diarization=False,
        )

        print("[2/4] Running PySceneDetect hybrid detection...")
        scenes = detect_scenes(str(source_video), str(scenes_json), detector="hybrid")

        print("[3/4] Running ClipRankingService hook & retention pacing...")
        ranker = ClipRankingService()
        ranked = ranker.rank_footage(
            transcript,
            scenes,
            campaign_name="Creator Retention Podcast",
            preferred_length_band="15-25",
            keep=20,
            select=5,
        )
        candidates = ranked["candidates"]
        top_clip = candidates[0]
        style = "dramatic"
        copy = generate_account_copy(
            style=style,
            campaign_name="Creator Retention Podcast",
            excerpt=top_clip.get("text") or "",
            hashtags=["#PodcastClips", "#CreatorWorkflow"],
            tags=[],
            disclosure="ClipOps Studio Example",
            hook_variant=1,
        )

        print("[4/4] Rendering 16:9 -> 9:16 vertical short via FFmpeg...")
        pkg_dir = tmp_dir / "rendered_pkg"
        render_info = render_account_package(
            source_video=str(source_video),
            start_sec=float(top_clip["start_sec"]),
            end_sec=float(top_clip["end_sec"]),
            style=style,
            duration_band=str(top_clip["duration_band"]),
            caption=copy["caption"],
            hook_text=copy["hook"],
            package_dir=str(pkg_dir),
            remotion_url=None,
            burn_captions=True,
        )
        if not render_info.get("ok"):
            raise RuntimeError(f"Render failed: {render_info}")
        shutil.copy2(Path(render_info["video_path"]), rendered_clip)

    _build_frame_strip(source_video, rendered_clip, frame_strip)
    _build_gif_preview(rendered_clip, rendered_gif)

    src_bytes = source_video.stat().st_size
    ren_bytes = rendered_clip.stat().st_size
    gif_bytes = rendered_gif.stat().st_size
    src_sha = sha256(source_video.read_bytes()).hexdigest()
    ren_sha = sha256(rendered_clip.read_bytes()).hexdigest()
    top_hook_score = top_clip["rank_report"]["hook_score"]
    top_pacing = top_clip["retention_pacing"]

    summary = {
        "example_name": "Three-Scene Spoken Podcast Demo (16:9 -> 9:16)",
        "source_video": {
            "path": source_video.relative_to(REPO_ROOT).as_posix(),
            "resolution": "1280x720",
            "duration_sec": round(_ffprobe_duration(source_video), 3),
            "size_bytes": src_bytes,
            "sha256": src_sha,
            "scenes": scene_durations,
        },
        "pipeline_outputs": {
            "transcript_engine": transcript.get("engine"),
            "transcript_segments": len(transcript.get("segments", [])),
            "word_segments": len(transcript.get("word_segments", [])),
            "detected_scenes_engine": scenes.get("engine"),
            "detected_scenes": scenes.get("scenes", []),
            "candidates": candidates,
            "selected_top_clip": {
                **top_clip,
                "style": style,
                "hook_text": copy["hook"],
                "caption": copy["caption"],
            },
            "transcript_preview": [
                {
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text"),
                }
                for seg in transcript.get("segments", [])
            ],
        },
        "rendered_output": {
            "path": rendered_clip.relative_to(REPO_ROOT).as_posix(),
            "resolution": "1080x1920",
            "duration_sec": round(_ffprobe_duration(rendered_clip), 3),
            "size_bytes": ren_bytes,
            "sha256": ren_sha,
            "render_info": render_info,
            "frame_strip": frame_strip.relative_to(REPO_ROOT).as_posix(),
            "gif_preview": rendered_gif.relative_to(REPO_ROOT).as_posix(),
            "gif_size_bytes": gif_bytes,
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    readme_text = f"""# Sample Podcast Clip Example (16:9 -> 9:16 End-to-End)

Generated by [`scripts/build_podcast_example.py`](../../scripts/build_podcast_example.py) using local Windows TTS (`Microsoft David Desktop` and `Microsoft Zira Desktop`) + FFmpeg and processed through the real ClipOps pipeline:

- **Input**: `source_podcast_16x9.mp4` (`1280x720`, `{summary['source_video']['duration_sec']}s`, `{src_bytes:,}` bytes)
- **Transcription**: `{transcript.get('engine')}` -> `{len(transcript.get('segments', []))}` segments, `{len(transcript.get('word_segments', []))}` word timestamps
- **Scene Detection**: `PySceneDetect` (`{scenes.get('detector', 'hybrid')}`) -> `{len(scenes.get('scenes', []))}` scenes
- **Top Candidate**: `{top_clip['start_sec']}s -> {top_clip['end_sec']}s` (`total_score={top_clip['total_score']}`, `hook_score={top_hook_score}`, `wpm={top_pacing['wpm']}`, `pacing={top_pacing['pacing_label']}`)
- **Rendered Short**: [`docs/proof/example-rendered-clip.mp4`](../../docs/proof/example-rendered-clip.mp4) (`1080x1920`, `{summary['rendered_output']['duration_sec']}s`, `{ren_bytes:,}` bytes)
"""
    (example_dir / "README.md").write_text(readme_text, encoding="utf-8")
    print(f"Done. Source: {src_bytes} bytes | Rendered 9:16: {ren_bytes} bytes | GIF: {gif_bytes} bytes")


if __name__ == "__main__":
    main()
