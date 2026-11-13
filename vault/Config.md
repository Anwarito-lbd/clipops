---
tags:
  - config
---

# Configuration & Environment

Read by [[Ingest]], [[Transcription]], [[Editing]], [[Remotion]], [[Export]], and [[OperatorUI]]. Model identifiers live in [[Models]].

`apps/api/app/config.py` loads `.env` from the repository root or current working directory:

| Setting | Default | Purpose |
| --- | --- | --- |
| `CLIPOPS_ENV` | `development` | `production` refuses weak JWT or missing bcrypt hash (`audit_settings`) |
| `DATABASE_URL` | `sqlite:///./clipops.db` | Local SQLite or Postgres 15 via `docker-compose.yml` |
| `CELERY_EAGER` | `true` | Runs `process_asset` inline without requiring Redis |
| `WHISPERX_MODEL` / device / compute | `medium` / `cuda` / `float16` | ASR model passed to `transcribe_video` (Operator Studio defaults to `tiny` CPU `int8` locally) |
| `REMOTION_URL` | `http://127.0.0.1:3100` | Optional [[Remotion]] caption compositing service |
| `STORAGE_ROOT` | `storage/` | Local source & export packages |
| `MAX_UPLOAD_MB` | `512` | Upload streaming cap |
| `CLIPOPS_FONTFILE` | auto-detected | Optional override for FFmpeg `drawtext` font path |

Run `python scripts/rotate_secrets.py --print-password` before any shared deployment. See [[EXAMPLES]] for observed runtime readiness outputs.
