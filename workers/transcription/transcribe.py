"""WhisperX → faster-whisper → heuristic transcription."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _heuristic_transcript(video_path: str, duration: float | None = None) -> dict:
    dur = duration or 60.0
    words = []
    text_parts = [
        "Wait until you see this.",
        "Here is what nobody tells you.",
        "The surprising part is next.",
        "That changes everything.",
        "Here is the payoff.",
    ]
    t = 0.0
    segments = []
    for i, sentence in enumerate(text_parts):
        start = t
        end = min(t + max(3.0, dur / len(text_parts)), dur)
        segments.append({"start": start, "end": end, "text": sentence, "speaker": f"SPEAKER_{i % 2}"})
        for w in sentence.split():
            words.append({"word": w, "start": start, "end": min(start + 0.35, end)})
            start += 0.35
        t = end
    return {"segments": segments, "word_segments": words, "language": "en", "engine": "heuristic"}


def _probe_duration(video_path: str) -> float | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            text=True,
        )
        return float(out.strip())
    except Exception:
        return None


def _via_whisperx(video_path: str, model: str, device: str, compute_type: str) -> dict:
    import whisperx  # type: ignore

    audio = whisperx.load_audio(video_path)
    asr = whisperx.load_model(model, device, compute_type=compute_type)
    result = asr.transcribe(audio, batch_size=8)
    align_model, metadata = whisperx.load_align_model(
        language_code=result.get("language", "en"), device=device
    )
    result = whisperx.align(
        result["segments"], align_model, metadata, audio, device, return_char_alignments=False
    )
    try:
        diarize = whisperx.DiarizationPipeline(device=device)
        diarize_segments = diarize(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)
    except Exception:
        pass
    return {
        "segments": result.get("segments", []),
        "word_segments": result.get("word_segments", []),
        "language": result.get("language", "en"),
        "engine": "whisperx",
    }


def _via_faster_whisper(video_path: str, model: str, device: str, compute_type: str) -> dict:
    from faster_whisper import WhisperModel  # type: ignore

    # Map ClipOps model names; medium is a good 8GB default
    name = model if model in {"tiny", "base", "small", "medium", "large-v2", "large-v3"} else "medium"
    # Prefer CUDA when requested; fall back to CPU int8
    try:
        wm = WhisperModel(name, device=device, compute_type=compute_type)
    except Exception:
        wm = WhisperModel(name, device="cpu", compute_type="int8")

    segments_iter, info = wm.transcribe(video_path, word_timestamps=True, vad_filter=True)
    segments = []
    words = []
    for seg in segments_iter:
        segments.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": (seg.text or "").strip(),
                "speaker": "SPEAKER_0",
            }
        )
        for w in seg.words or []:
            words.append(
                {
                    "word": w.word,
                    "start": float(w.start),
                    "end": float(w.end),
                }
            )
    return {
        "segments": segments,
        "word_segments": words,
        "language": getattr(info, "language", "en"),
        "engine": "faster-whisper",
    }


def transcribe_video(
    video_path: str,
    output_json: str,
    model: str = "medium",
    device: str = "cuda",
    compute_type: str = "float16",
) -> dict:
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    duration = _probe_duration(video_path)
    errors: list[str] = []

    for name, fn in (
        ("whisperx", lambda: _via_whisperx(video_path, model, device, compute_type)),
        ("faster-whisper", lambda: _via_faster_whisper(video_path, model, device, compute_type)),
    ):
        try:
            payload = fn()
            if payload.get("segments"):
                Path(output_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
                return payload
            errors.append(f"{name}: empty segments")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    payload = _heuristic_transcript(video_path, duration)
    payload["fallback_reason"] = " | ".join(errors) or "no engine"
    Path(output_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import sys

    video, out = sys.argv[1], sys.argv[2]
    print(json.dumps(transcribe_video(video, out)))
