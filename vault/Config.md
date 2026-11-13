---
tags:
  - config
---

# Config

Read by [[Ingest]], [[Transcription]], [[Editing]], and [[Export]]. Model ids are listed in [[Models]].

`apps/api/app/config.py` loads `.env` from the repo root or the working directory. Defaults that matter for a local run:

| Setting | Default in code |
| --- | --- |
| `CLIPOPS_ENV` | `development` |
| `OPERATOR_EMAIL` | `operator@clipops.local` |
| `OPERATOR_PASSWORD` | `changeme` until `scripts/rotate_secrets.py` writes a bcrypt hash |
| `DATABASE_URL` | `sqlite:///./clipops.db` |
| `CELERY_EAGER` | `true` (pipeline runs inside the request; Redis is optional) |
| `WHISPERX_MODEL` / device / compute | `medium` / `cuda` / `float16` |
| `REMOTION_URL` | `http://127.0.0.1:3100` |
| `STORAGE_ROOT` | repo `storage/` |
| `MAX_UPLOAD_MB` | 512 |
| `PLATFORM_FEE_MULTIPLIER` | 0.93 |
| `BUDGET_UTILISATION_REJECT_THRESHOLD` | 0.90 |

Production startup calls `audit_settings` and refuses a weak JWT or a missing password hash (`apps/api/app/main.py`). Development prints the warning and still boots. The local health check did that: `security_ok` true, message `demo password in use — rotate before any shared deploy`.

`docker-compose.yml` starts Postgres 15, Redis 7, the API image, a Celery worker, the Remotion image, and n8n. Postgres init runs both SQL files: `supabase/migrations/20260727100000_init.sql` and `20260727120000_operator_mode.sql`. The API also calls `Base.metadata.create_all`, so SQLite does not need those files.

Stack readiness on `GET /health` is six booleans: ffmpeg, CUDA torch, WhisperX or faster-whisper, PySceneDetect, Remotion, and Redis or eager Celery. On the audit machine that was 4 of 6, reported as `readiness_pct` 67, mode `eager_inline`. Torch was not installed (`No module named 'torch'`). WhisperX was not installed. faster-whisper, PySceneDetect, and ffmpeg were.

See [[EXAMPLES]] for that health JSON.
