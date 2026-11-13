---
tags:
  - pipeline
---

# Transcription & WhisperX Forced Alignment

Upstream: [[Ingest]] · Downstream: [[SceneDetection]], [[Scoring]], [[RetentionPacing]] · Configuration: [[Config]], [[Models]]

Implemented in `workers/transcription/transcribe.py` (`transcribe_video`).

## Fallback Chain

1. **WhisperX (`_via_whisperx`)** — loads Silero VAD (`vad_method="silero"` to avoid Windows `pyannote`/`k2` breakage), transcribes batches, then runs **phoneme-level forced alignment** via `whisperx.load_align_model` and `whisperx.align(..., return_char_alignments=False)` to produce exact word-level `[start, end]` timestamps (`word_segments`).
2. **faster-whisper (`_via_faster_whisper`)** — extracts 16 kHz mono WAV via FFmpeg (`_ffmpeg_wav`), decodes to contiguous `float32` PCM (`_wav_to_float32`), and passes the NumPy array directly into `WhisperModel.transcribe(..., word_timestamps=True, vad_filter=True)`. Passing PCM avoids `faster-whisper` 1.2 calling `av.open(..., metadata_errors="ignore")`, which PyAV 19 removed.
3. **Heuristic fallback (`_heuristic_transcript`)** — if WhisperX is absent or an audio track is silent/pure-tone (empty ASR segments), produces deterministic timed segments and word timestamps across the probed duration and records `fallback_reason`.

## Why Word Timestamps Matter Downstream

- [[RetentionPacing]] uses `word_segments` to measure spoken coverage vs dead air (`spoken_sec / duration_sec`) and 3-second hook word density.
- [[Remotion]] and [[Editing]] align hook overlays and caption cadence to segment boundaries.
- [[OperatorUI]] renders interactive word chips `[start] word` in the Transcript Inspector.

See [[EXAMPLES]] for real engine diagnostics recorded on CPU (`int8`).
