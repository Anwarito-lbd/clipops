# ClipOps

Monorepo for ClipOps Operator Mode. See `README.md` and `docs/`.

## Cursor Cloud specific instructions

### Ready stack (one command)

```bash
./scripts/start_dev.sh
```

Starts **API :8000**, **Dashboard :3000**, **Remotion :3100**. Default SQLite + `CELERY_EAGER=true` (no Redis). Seeds **3 TikTok + 3 YouTube + 1 CR**.

Operator login: `operator@clipops.local` + password from `scripts/rotate_secrets.py --print-password`.

### What “ready” means

| Layer | Ready when |
|---|---|
| Software stack | `/health` → `media.readiness_pct` **100** (ffmpeg + ASR + scenes + Remotion + eager) |
| Operator dry-run | Approve → upload → export → mark posted/submitted (go-live score rises) |
| Never automated | CR Join / Submit / Cash-out — ClipOps only sends **JOIN NOW** / **CASHOUT NOW** alerts |

CUDA/WhisperX is **optional** (`gpu_optional`). CPU + faster-whisper is enough.

### Manual start (if not using start_dev.sh)

```bash
# Remotion
cd templates && npm start
# API
cd apps/api && PYTHONPATH="/workspace:$PWD" ../../apps/api/.venv/bin/uvicorn app.main:app --reload --port 8000
# Dashboard
cd apps/dashboard && npm run dev
```

### Multi-platform + Scrapling + video

- Accounts: `/accounts` · `GET/POST /api/accounts`
- Discover: extension **or** `POST /api/operator/discover/scrapling`
- Captions: Remotion karaoke; optional `ENABLE_TTS_COMMENTARY=true` for commentary accounts
- Docs: `docs/CONTENT_REWARDS.md`, `docs/VIDEO_QUALITY.md`, `docs/OAUTH_POSTING.md`

### Tests

`apps/api/.venv/bin/python -m pytest tests/`
