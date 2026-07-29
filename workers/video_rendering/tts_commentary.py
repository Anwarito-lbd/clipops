"""Optional Edge TTS commentary overlay — campaign footage only (MoneyPrinterTurbo-inspired).

Used for the *commentary* account style: synthesize a short reaction line and
mix it under the original audio (ducked). Never replaces brand footage with stock.
Requires ``edge-tts``; fails soft if missing so the pipeline still exports video.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


def commentary_script(*, hook_text: str, excerpt: str = "", campaign_name: str = "") -> str:
    """Short spoken reaction — not a full MoneyPrinterTurbo stock-script rewrite."""
    hook = (hook_text or "").strip()
    if hook:
        # Keep TTS short so it fits clip intros
        return hook[:180]
    if excerpt:
        return f"Okay but look at this — {excerpt[:120]}"
    if campaign_name:
        return f"My honest take on {campaign_name}."
    return "Okay but can we talk about this?"


async def _synthesize_edge(text: str, out_mp3: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_mp3))


def synthesize_commentary_mp3(
    *,
    text: str,
    out_path: str | Path,
    voice: str = "en-US-JennyNeural",
) -> Path | None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(_synthesize_edge(text, out, voice))
    except Exception:
        return None
    if out.exists() and out.stat().st_size > 0:
        return out
    return None


def mix_commentary_audio(
    *,
    video_in: str | Path,
    commentary_mp3: str | Path,
    video_out: str | Path,
    ffmpeg_path: str = "ffmpeg",
    voice_volume: float = 0.85,
    bed_volume: float = 0.55,
) -> bool:
    """Mix TTS over original audio (ducked bed). Keeps video stream from campaign cut."""
    vin = Path(video_in)
    mp3 = Path(commentary_mp3)
    vout = Path(video_out)
    if not vin.exists() or not mp3.exists():
        return False
    # amix: original (quieter) + TTS; duration = first (video)
    filter_complex = (
        f"[0:a]volume={bed_volume}[a0];"
        f"[1:a]volume={voice_volume},afade=t=in:st=0:d=0.15[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(vin),
                "-i",
                str(mp3),
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(vout),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    return vout.exists() and vout.stat().st_size > 0


def maybe_apply_tts_commentary(
    *,
    style: str,
    enabled: bool,
    video_path: Path,
    hook_text: str,
    excerpt: str = "",
    campaign_name: str = "",
    package_dir: Path,
    ffmpeg_path: str = "ffmpeg",
    voice: str = "en-US-JennyNeural",
) -> dict:
    """Apply TTS only for commentary style when enabled. Soft-fail otherwise."""
    result = {
        "tts_applied": False,
        "tts_path": None,
        "tts_error": None,
        "video_path": str(video_path),
    }
    if not enabled or (style or "").lower() != "commentary":
        return result
    if not video_path.exists() or video_path.stat().st_size == 0:
        result["tts_error"] = "empty_video"
        return result
    text = commentary_script(hook_text=hook_text, excerpt=excerpt, campaign_name=campaign_name)
    mp3 = package_dir / "commentary_tts.mp3"
    synth = synthesize_commentary_mp3(text=text, out_path=mp3, voice=voice)
    if not synth:
        result["tts_error"] = "edge_tts_unavailable_or_failed"
        return result
    mixed = package_dir / "video_tts.mp4"
    ok = mix_commentary_audio(
        video_in=video_path,
        commentary_mp3=synth,
        video_out=mixed,
        ffmpeg_path=ffmpeg_path,
    )
    if not ok:
        result["tts_error"] = "ffmpeg_mix_failed"
        result["tts_path"] = str(synth)
        return result
    mixed.replace(video_path)
    result["tts_applied"] = True
    result["tts_path"] = str(synth)
    result["tts_text"] = text
    return result
