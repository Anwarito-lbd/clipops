---
tags:
  - examples
---

# Verified Pipeline Examples

Linked from [[Home]], [[Ingest]], [[Transcription]], [[SceneDetection]], [[Scoring]], [[RetentionPacing]], [[Hooks]], [[Editing]], [[Remotion]], [[Export]], [[OperatorUI]], [[Config]], [[Models]].

All values below were captured from actual runs on this repository (no GPU, no WhisperX, no Remotion server running).

## 1. Operator Studio Demo (`24s` Multi-Scene Reel)

Captured via `scripts/capture_operator_ui.py` (`docs/proof/studio-demo-summary.json`):

- **Source Probe**: `source_demo.mp4` (`24.0s`, `1080×1920` @ `30.0 fps`, `h264`/`aac`, `462,919` bytes)
- **Scene Detection (`pyscenedetect`, `content`)**: 3 scenes detected (`0.0–8.0s`, `8.0–16.0s`, `16.0–24.0s`, `cut_count: 2`)
- **Transcription**: `engine: heuristic` (`fallback_reason: whisperx: No module named 'whisperx' | faster-whisper: empty segments`), with `demo_script_overlay: true` and word-level timestamps across 3 segments
- **Top Candidate (`clip-1`, `8.0–16.0s`)**:
  - `total_score`: `70.4` (`MEDIUM`), `hook_type`: `surprising_fact`, `style`: `dramatic`
  - `retention_pacing`: `44` words, `wpm: 330.0` (`FAST_ENERGETIC`), `dead_air_ratio: 0.1` (`0.8s`), `hook_window_words_3s: 6`
- **Dry-Run Filtergraph**: resolved `C:/Windows/Fonts/arial.ttf`, `scale=iw*1.12:ih*1.12,crop=1080:1920`, `loudnorm=I=-16:TP=-1.5:LRA=11`
- **Human Approval & Render**: operator approved `clip-1` (`compliance_preview.passed: true`), local FFmpeg wrote `168,868`-byte `video.mp4` (`1080×1920`, SHA-256 `a91d7fb8986a322c...`)

![Operator Studio UI](../docs/images/operator-ui.png)

## 2. Offline Worker Script (`scripts/demo_offline.py docs/proof`)

Recorded in `docs/proof/demo-summary.json`:

- **Source**: `12.000000s`, `138,180` bytes, `1080×1920` H.264/AAC
- **PySceneDetect**: 3 cuts (`0–4s`, `4–8s`, `8–12s`)
- **Brief Score (VoltPop Summer Push)**: `65.0`, recommendation `AVOID`, `reject_reasons: []` (below `70` threshold)
- **Top Clip (`8–12s`)**: `67.3` (`surprising_fact`, `MEDIUM`)
- **Dramatic Render**: `4.0s`, `88,394` bytes (`render_error: null`), compliance held on `4.0s not in [20, 45]`

![Sample Dramatic Frame](../docs/proof/sample-frame.png)

## 3. Test Suite (`docs/proof/pytest.txt`)

- `.venv/Scripts/python.exe -m pytest tests -v` → **`25 passed, 4 warnings in 29.52s`** (includes `tests/test_core.py`, `tests/test_smoke_pipeline.py`, and `tests/test_studio_and_vault.py`).
