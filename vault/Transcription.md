---
tags:
  - pipeline
---

# Transcription

After [[Ingest]], `process_asset` calls `transcribe_video`, then [[Scoring]] uses the segments. Model names are in [[Models]]. The engine string from a real silent clip is in [[EXAMPLES]].

The worker tries WhisperX, then faster-whisper, then a heuristic transcript. Empty segments count as a failure of that engine, so a tone with no speech still produces segments the ranker can score.

```239:258:workers/transcription/transcribe.py
    for name, fn in (
        (
            "whisperx",
            lambda: _via_whisperx(
                video_path, model, device, compute_type, hf_token, enable_diarization
            ),
        ),
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
```

faster-whisper 1.2 decodes file paths with `av.open(..., metadata_errors="ignore")`. PyAV 19 removed that keyword. The worker extracts 16 kHz mono PCM with ffmpeg and passes a float32 array instead, which skips that `av.open` call (`_wav_to_float32` in the same file).

WhisperX diarization runs only when `HF_TOKEN` is set. This audit did not set one. See [[Config]].

Scene windows are a separate step, still before ranking: PySceneDetect `ContentDetector(threshold=27.0)`, or fixed 8 second windows if that import fails (`workers/scene_detection/detect.py`).

Next: [[Scoring]].
