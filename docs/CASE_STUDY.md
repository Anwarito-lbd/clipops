# Case Study: Keeping the Last Click Human in an AI Short-Form Video Workstation

ClipOps is an ethical short-form video clipping & editing workstation built for a single creator or editor. Given a creative brief and a long-form source video, ClipOps transcribes speech with word-level timestamps, detects scene cut boundaries, scores hooks and retention pacing, renders up to three distinct `9:16` editorial packages (`dramatic`, `educational`, `commentary`) with compliance disclosures baked in, and **stops strictly before publishing**. Approval, posting, submission, and payout confirmation remain human clicks. `GET /health` reports `automation_boundary: human_approval_manual_posting` (and the local Operator Studio UI reports `human_approval_manual_publish`).

## What ClipOps Refuses to Automate

Publishing actions are intentionally absent from the state machine:
- `ALLOWED_TRANSITIONS` in `packages/shared_types/constants.py` has no transition that auto-posts or auto-submits (`EXPORTED -> MANUALLY_POSTED` requires the operator to paste their own published URL).
- `browser-extension/manifest.json` operates strictly as a read-only brief/asset helper on an already logged-in tab — never auto-clicking Join, Submit, or Withdraw.
- Approving a brief returns explicit next steps reminding the operator to join manually.
- Rather than cloning one clip across accounts, `process_asset` and `StudioService` assign top-ranked windows round-robin across three editorial styles (`dramatic`, `educational`, `commentary`) with distinct zooms, caption layouts, and hook templates (`assert_versions_not_identical` enforces unique SHA-256 export hashes).

## How Clips Are Scored Without an LLM

ClipOps avoids opaque, slow, or expensive LLM calls in the scoring loop:

1. **Brief Scoring (`CampaignScoringService`)**: Weighted sum across `SCORE_WEIGHTS` (`remaining_budget` 20, `audience_match` 20, `cpm` 15, `footage_quality` 15, `viral_potential` 15, `requirement_simplicity` 10, `competition` 5). Explicit hard-reject flags (budget utilisation $\ge 0.90$, fake engagement, missing rights, geography mismatch) force `is_recommended = False`. Eligible briefs scoring under `70` are labeled `AVOID` (as observed on the `65.0` VoltPop brief).
2. **Scene Cut Detection (`workers/scene_detection/detect.py`)**: PySceneDetect runs `AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=15)` and/or `ContentDetector(threshold=27.0)` (with `hybrid` fallback and `8.0s` fixed-window fallback if OpenCV/PySceneDetect fails).
3. **Hook & Retention Pacing (`packages/services/clip_ranking.py`)**: Overlapping transcript segments are evaluated with deterministic regexes (`hook`, `curiosity`, `conflict`, `emotion`, `payoff`, `clarity`, `fit`), weighted (`0.18` hook + `0.18` payoff + `0.12`×4 + `0.10` fit + `0.06` duration) minus a dead-air penalty. `compute_retention_pacing` tracks speaking rate (`[125, 185]` WPM optimal), spoken coverage ratio from word timestamps, and 3-second hook word density.

## Engineering Sharp Edges Found & Fixed

- **PyAV 19 + `faster-whisper` 1.2 decoding crash**: `faster-whisper` calls `av.open(..., metadata_errors="ignore")`, which PyAV 19 removed. `workers/transcription/transcribe.py` extracts 16 kHz mono WAV via FFmpeg and feeds a contiguous `float32` PCM array directly to `WhisperModel.transcribe(..., word_timestamps=True)`, skipping `av.open` completely.
- **FFmpeg `drawbox` `w`/`h` self-reference (exit 234)**: Inside `drawbox`, `w` and `h` refer to the box itself, not the frame. Switching to `iw` and `ih` fixed the 0-byte `commentary` render.
- **Windows FFmpeg `drawtext` crash (`0xC0000005` / `3221225477`)**: On Windows FFmpeg builds lacking Fontconfig config files, invoking `drawtext` without an explicit `fontfile` crashes with an access violation. Adding `_resolve_fontfile()` + `_escape_filter_path()` (`fontfile='C\:/Windows/Fonts/arial.ttf'`) inside `build_filtergraph()` made all three editorial styles render cleanly on both Windows and Linux.
- **Fail-closed compliance gates**: `run_compliance_check` treats unverified logos (`has_logo is None` when `requires_logo=True`) and out-of-band durations (e.g., `4.0s not in [20, 45]`) as compliance holds in `REVIEW_REQUIRED` rather than silently exporting non-compliant cuts.

## Lightweight Local NLE Operator Studio + Real 16:9→9:16 Podcast Example + Obsidian Brain

To make every stage inspectable without standing up Postgres, Redis, or Next.js, ClipOps pairs `apps/operator-ui/` (FastAPI dark-mode NLE Studio + `cli.py`) with a zero-orphan 14-note Obsidian Knowledge Graph (`vault/`). Applying UI craft guidance from `anthropics/skills@frontend-design` (discovered via `npx skills add https://github.com/vercel-labs/skills --skill find-skills`), the Operator Studio provides:
- A multi-track NLE sequence (`V1 SCENES`, `A1 HOOK / WAVE` combining FFmpeg 72-bin PCM waveforms with an SVG hook-score curve, and `T1 CUT SPAN`),
- A toggleable `9:16` crop & platform safe-zone overlay over `16:9` feeds (`TITLE / HOOK ZONE`, `UI RAIL`, `CAPTIONS SAFE MARGIN`),
- Live word-level transcript highlighting synced to `video.timeupdate` with click-to-seek,
- Transport controls + NLE keyboard shortcuts (`Space`, `J`/`K`/`L`, `A`, `R`, `D`), and
- One-click **Load 16:9 Podcast Example** (`examples/sample_podcast_clip/source_podcast_16x9.mp4`), which executes `faster-whisper` (`4` segments, `83` word timestamps), `PySceneDetect` (`3` scenes), `ClipRankingService` (`total_score=66.1`, `hook_score=90.0`), and FFmpeg `1080×1920` vertical export (`docs/proof/example-rendered-clip.mp4`).
