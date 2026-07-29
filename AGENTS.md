# ClipOps

Monorepo for ClipOps "Operator Mode" (short-form video campaign pipeline: approve → post → submit → cash out). See `README.md` for the product overview and `docs/` for workflow/ops details.

## Cursor Cloud specific instructions

The `README.md` quick start is Windows/PowerShell-oriented. On this Linux VM use the notes below.

### Services

| Service | Path | Dev command | Port | Required |
|---|---|---|---|---|
| API (FastAPI) | `apps/api` | see below | 8000 | Yes |
| Dashboard (Next.js) | `apps/dashboard` | `npm run dev` | 3000 | Yes |
| Remotion render | `templates` | `npm start` (`node server.js`) | 3100 | Optional (FFmpeg burns captions if down) |
| Redis + Celery worker | — | via `docker-compose.yml` | 6379 | Optional (default `CELERY_EAGER=true` runs the pipeline inline) |
| Postgres / n8n | — | via `docker-compose.yml` | 54322 / 5678 | Optional (default DB is SQLite) |

### Running the API (non-obvious)

The Python venv lives at `apps/api/.venv`. `PYTHONPATH` must include the repo root AND `apps/api` or imports fail:

```bash
cd apps/api
PYTHONPATH="/workspace:$PWD" ../../apps/api/.venv/bin/uvicorn app.main:app --reload --port 8000
```

- Default config runs zero-dependency: SQLite (`clipops.db`) + `CELERY_EAGER=true` (pipeline runs inside the API process, no Redis/Celery worker needed).
- `GET /health` reports media-stack readiness (`torch`/CUDA are absent on this CPU VM — WhisperX falls back to faster-whisper → heuristic; this is expected).

### Auth / login

- `.env` is gitignored; it is created from `.env.example` and secrets are rotated during setup. It persists in the VM snapshot.
- Operator login: `operator@clipops.local`. The password is a bcrypt hash in `.env` (`OPERATOR_PASSWORD_HASH`) and the plaintext is only shown once at rotation. To get a fresh password, run:

```bash
apps/api/.venv/bin/python scripts/rotate_secrets.py --print-password
```

Then restart the API so it reloads `.env`.

### Testing / lint

- Tests: `apps/api/.venv/bin/python -m pytest tests/` (pure-Python, uses SQLite + a synthesized FFmpeg clip; no services required).
- `npm run lint` in `apps/dashboard` is **interactive** (no ESLint config is committed) and cannot run non-interactively. Use `npm run build` for type/route checking instead.

### Demo data

The dashboard Home page "Seed demo top 3" button (`POST /api/operator/demo/seed-top3`) creates sample campaigns you can approve — useful for smoke-testing the operator flow without the browser extension.
