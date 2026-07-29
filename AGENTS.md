# ClipOps

Monorepo for ClipOps Operator Mode. See `README.md` and `docs/`.

## Cursor Cloud specific instructions

### Services

| Service | Path | Dev command | Port | Required |
|---|---|---|---|---|
| API (FastAPI) | `apps/api` | `PYTHONPATH="/workspace:$PWD" ../../apps/api/.venv/bin/uvicorn app.main:app --reload --port 8000` | 8000 | Yes |
| Dashboard | `apps/dashboard` | `npm run dev` | 3000 | Yes |
| Remotion | `templates` | `npm start` | 3100 | Optional |

Default: SQLite + `CELERY_EAGER=true` (no Redis). Seeds **3 TikTok + 3 YouTube + 1 CR** accounts.

### Multi-platform + Scrapling

- Accounts UI: `/accounts`. API: `GET/POST /api/accounts`.
- Mark posted accepts `post_url` (TikTok or YouTube).
- Public discover: `POST /api/operator/discover/scrapling` ([D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) Fetcher only).
- Approve → `join_now` alert; payout-watch → `cashout_now`. **Bot cannot Join or cash-out.**
- Docs: `docs/CONTENT_REWARDS.md`, `docs/OAUTH_POSTING.md`, `docs/VIDEO_QUALITY.md`.

### Video (MoneyPrinterTurbo borrow)

- Stronger Remotion karaoke subtitles + FFmpeg outline burn-in.
- Optional Edge TTS for **commentary** style only: `ENABLE_TTS_COMMENTARY=true` (campaign footage, not stock).

### Auth

`.env` from `.env.example` + `scripts/rotate_secrets.py --print-password`. Login `operator@clipops.local`.

### Tests

`apps/api/.venv/bin/python -m pytest tests/`
