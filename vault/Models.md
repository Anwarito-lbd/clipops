---
tags:
  - config
---

# Models

What “model” means in this repo: an ASR checkpoint name, a caption style, or a SQLAlchemy row. None of the ranking math calls an external LLM. [[Transcription]] and [[Editing]] are the two places a model name is used. [[Config]] holds the env vars.

## Speech

`transcribe_video` passes `settings.whisperx_model` through. faster-whisper only accepts `tiny`, `base`, `small`, `medium`, `large-v2`, and `large-v3`; anything else becomes `medium` (`workers/transcription/transcribe.py`). The offline demo and the API session both requested `tiny` on CPU int8 so the run would not download a larger checkpoint. WhisperX was absent, so the chain never loaded a WhisperX checkpoint. Diarization is the WhisperX `DiarizationPipeline` and only runs with an HF token.

The heuristic fallback does not load weights. It splits the probed duration across five fixed sentences, starting with “Wait until you see this.” That is why a silent color-bar file still ranks.

## Picture

Account styles are `dramatic`, `educational`, and `commentary` (`ACCOUNT_STYLES` in `packages/shared_types/constants.py`). Remotion compositions of the same names live under `templates/`. The render service is `templates/server.js`: `GET /health` and `POST /render` on port 3100. This audit did not start it.

## Rows

`apps/api/app/db.py` is the working schema for SQLite and for `create_all`: `SocialAccount`, `Campaign`, `CampaignRequirement`, `SourceAsset`, `ClipCandidate`, `ClipVersion`, `Render`, `ComplianceCheck`, plus operator tables for discoveries, notifications, performance, and production events. Three TikTok accounts are seeded on startup, one per style. The review session addressed them as TikTok 3 Commentary, TikTok 1 Dramatic, and TikTok 2 Educational.

Forecast defaults, used when no performance rows exist, are in `ForecastService.forecast`: `avg_views_per_clip=8210.0`, `planning_cpm=2.0`, `approval_rate=0.7`, `clips_per_day_capacity=7.5`. Home showed 8210 and £2 because the database had no view rows. Those are planning constants, not measured clip performance.

[[Home]]
