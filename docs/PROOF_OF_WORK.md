# Proof of Work — ClipOps Verification Log

All checks, renders, and captures below were executed directly against this repository on `2026-11-13` (branch `cursor/portfolio-proof-53d8`, Windows 11, Python `3.12.10`, Node `v24.19.0`, FFmpeg `8.1.2`).

## 1. Engineering Fixes & Deliverables Implemented

- **Cross-Platform FFmpeg `drawtext` Fix (`workers/video_rendering/render.py`)**:
  - Windows FFmpeg 8.1.2 crashed (`0xC0000005` / `3221225477`) when `drawtext` ran without a Fontconfig config or explicit `fontfile`.
  - Added `_resolve_fontfile()` and `_escape_filter_path()` (`fontfile='C\:/Windows/Fonts/arial.ttf'`) plus `build_filtergraph()` for deterministic dry-run command inspection.
- **PySceneDetect Adaptive + Content + Hybrid Modes (`workers/scene_detection/detect.py`)**:
  - Added `AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=15)` alongside `ContentDetector(threshold=27.0)` and `hybrid` fallback; replaced deprecated `start.get_seconds()` with `start.seconds`.
- **Retention Pacing Math (`packages/services/clip_ranking.py`)**:
  - Added `compute_retention_pacing()` computing `wpm`, `ideal_wpm_range=[125, 185]`, `spoken_sec`, `dead_air_sec`, `dead_air_ratio`, `hook_window_words_3s`, and `pacing_label`.
- **Compliance Gate Detail Accuracy (`packages/compliance_checker/checker.py`)**:
  - Fixed hardcoded `"not in"` / failure detail strings when `duration`, `external_music`, and `duplicate_export` checks pass.
- **Ethical Workstation Reframing**:
  - Updated `packages/posting_queue/router.py`, `packages/services/forecast.py`, `apps/api/app/readiness.py`, `apps/dashboard/app/queue/page.tsx`, `docs/USER_WORKFLOW.md`, `docs/CASE_STUDY.md`, `README.md`, and `vault/` to frame ClipOps strictly as a single-creator ethical video clipping & editing workstation with human approval gates (`human_approval_manual_posting` / `human_approval_manual_publish`).
- **Lightweight Local NLE Operator Studio UI + CLI (`apps/operator-ui/`)**:
  - Upgraded UI following `anthropics/skills@frontend-design` (`npx skills add https://github.com/vercel-labs/skills --skill find-skills`, installed outside repo): multi-track NLE sequence (`V1 Scenes`, `A1 72-bin RMS Waveform + SVG Hook Curve`, `T1 Cut Span`), toggleable `9:16` crop & platform safe-zone overlay, live word-level transcript highlight + click-to-seek, SMPTE timecode HUD, NLE transport & keyboard shortcuts (`Space`, `J`/`K`/`L`, `A`, `R`, `D`), and one-click `POST /api/studio/sessions/example`.
- **Three-Scene `16:9` Spoken Podcast Example (`scripts/build_podcast_example.py`)**:
  - Synthesized `examples/sample_podcast_clip/source_podcast_16x9.mp4` (`1280×720`, `30.487s`, `355,881` bytes, `SHA-256: e96edbe343d2c8a7...`) using Windows `System.Speech` (`Microsoft David Desktop` + `Microsoft Zira Desktop`) + FFmpeg overlays.
  - Real offline `faster-whisper` (`tiny`, CPU `int8`) transcription (`4` segments, `83` word timestamps), `PySceneDetect` (`hybrid` -> `adaptive`, `3` scenes: `0–9.233s`, `9.233–21.767s`, `21.767–30.367s`), `ClipRankingService` (`cand-1` Scene 2 scored `66.1`, `hook_score=90.0`), and rendered `1080×1920` `docs/proof/example-rendered-clip.mp4` (`12.567s`, `316,968` bytes, `SHA-256: bc7dae99b0507280...`), `docs/proof/example-frame-strip.png`, `docs/proof/example-rendered-preview.gif` (`104,620` bytes), and `docs/proof/example-podcast-summary.json`.
- **ClipOps Brand Logo (`docs/images/clipops-logo.png`, `ui/logo.png`)**:
  - Generated custom `512×512` dark-mode studio emblem via `image-generator` (`generate_image`).
- **Zero-Orphan Obsidian Clipping Brain (`vault/`)**:
  - Expanded to 14 interconnected Markdown notes (`Home.md`, `Ingest.md`, `Transcription.md`, `SceneDetection.md`, `Scoring.md`, `Hooks.md`, `RetentionPacing.md`, `Editing.md`, `Remotion.md`, `OperatorUI.md`, `Export.md`, `Config.md`, `Models.md`, `EXAMPLES.md`) + `.obsidian/graph.json`.

## 2. Exact Verification Runs & Observed Outputs

| Check | Command | Observed Result |
| --- | --- | --- |
| **Pytest Full Suite** | `.venv\Scripts\python.exe -m pytest tests -v` | **`26 passed, 4 warnings in 47.29s`** (`docs/proof/pytest.txt`) |
| **Podcast E2E Pipeline** | `.venv\Scripts\python.exe scripts/build_podcast_example.py` | Exit `0` — `faster-whisper` (`4` segs, `83` words), `PySceneDetect` (`3` scenes), `1080×1920` render `316,968` B (`docs/proof/example-podcast-summary.json`) |
| **Obsidian Vault Integrity** | `test_obsidian_vault_zero_orphans_and_valid_links` + `scripts/render_vault_graph.py` | **`14` notes, `108` wikilinks, `0` orphans, `0` broken links** (`docs/images/vault-graph.png`) |
| **Offline Worker Demo** | `.venv\Scripts\python.exe scripts/demo_offline.py docs/proof` | Exit `0` — `12.0s` source (`138,180` B), `3` PySceneDetect cuts, `4.0s` dramatic render (`88,394` B, `render_error: null`), compliance held on `4.0s not in [20, 45]` (`docs/proof/demo-summary.json`) |
| **Operator Studio CLI Demo** | `.venv\Scripts\python.exe apps/operator-ui/cli.py demo --out-json docs/proof/cli-demo-summary.json` | Exit `0` — `24.0s` 3-scene source (`462,919` B), `clip-1` scored `70.4` (`surprising_fact`, `MEDIUM`), 13/13 compliance checks passed, rendered `168,868`-byte `video.mp4` (`SHA-256: a91d7fb8986a322c...`) |
| **Playwright Live UI Capture** | `.venv\Scripts\python.exe scripts/capture_operator_ui.py` | Exit `0` — captured NLE desktop (`1440×900`) `operator-ui.png` & `operator-ui-rendered.png`, mobile (`390×844`) `operator-ui-mobile.png`, walkthrough MP4 (`588,212` B) & GIF (`9,948,891` B), plus `docs/proof/studio-demo-summary.json` |
| **JavaScript Syntax Check** | `node --check apps/operator-ui/static/app.js; node --check templates/server.js; node --check browser-extension/background.js; node --check browser-extension/content.js` | Exit `0` across all 4 scripts |
| **JSON Manifest Validation** | `json.loads(...)` on `browser-extension/manifest.json`, `vault/.obsidian/graph.json`, `apps/dashboard/package.json`, `templates/package.json`, `workflows/n8n/clipops-notify.json` | Exit `0` — all valid JSON |

## 3. Visual & Proof Artifacts Added/Updated

- `docs/images/clipops-logo.png` & `ui/logo.png` (`512×512` PNG)
- `docs/images/operator-ui.png` (`1440×900` Playwright desktop capture: 16:9 feed + 9:16 safe guides + V1/A1/T1 timeline + live words)
- `docs/images/operator-ui-rendered.png` (`1440×900` Playwright desktop capture: 9:16 rendered cut + 13-point compliance gate + FFmpeg dry-run)
- `docs/images/operator-ui-mobile.png` (`390×844` Playwright Chromium mobile capture)
- `docs/images/operator-ui-walkthrough.mp4` (`588,212` bytes, Playwright screen recording transcoded via FFmpeg H.264)
- `docs/images/operator-ui-walkthrough.gif` (`9,948,891` bytes, FFmpeg palettegen/paletteuse preview)
- `docs/images/vault-graph.png` (`558,616` bytes, 14-node Obsidian link graph)
- `examples/sample_podcast_clip/source_podcast_16x9.mp4` (`355,881` bytes), `docs/proof/example-rendered-clip.mp4` (`316,968` bytes), `docs/proof/example-frame-strip.png`, `docs/proof/example-rendered-preview.gif` (`104,620` bytes), `docs/proof/example-podcast-summary.json`
- `docs/proof/pytest.txt`, `docs/proof/demo-summary.json`, `docs/proof/studio-demo-summary.json`, `docs/proof/cli-demo-summary.json`, `docs/proof/sample-frame.png`
