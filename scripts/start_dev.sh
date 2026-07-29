#!/usr/bin/env bash
# ClipOps local ready stack (Linux / Cursor Cloud)
# Starts API + Dashboard + Remotion. Does NOT start Redis/Celery (eager mode default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — run: apps/api/.venv/bin/python scripts/rotate_secrets.py --print-password"
fi

if [[ ! -x apps/api/.venv/bin/python ]]; then
  python3 -m venv apps/api/.venv
  apps/api/.venv/bin/python -m pip install -U pip
  apps/api/.venv/bin/python -m pip install -r apps/api/requirements.txt
fi

[[ -d apps/dashboard/node_modules ]] || npm install --prefix apps/dashboard
[[ -d templates/node_modules ]] || npm install --prefix templates

mkdir -p storage logs

echo "Starting Remotion :3100 ..."
(cd templates && npm start >"$ROOT/logs/remotion.log" 2>&1) &
echo $! >"$ROOT/logs/remotion.pid"

echo "Starting API :8000 ..."
(cd apps/api && PYTHONPATH="$ROOT:$PWD" "$ROOT/apps/api/.venv/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000 >"$ROOT/logs/api.log" 2>&1) &
echo $! >"$ROOT/logs/api.pid"

echo "Starting Dashboard :3000 ..."
(cd apps/dashboard && npm run dev -- --hostname 0.0.0.0 --port 3000 >"$ROOT/logs/dashboard.log" 2>&1) &
echo $! >"$ROOT/logs/dashboard.pid"

echo "Waiting for health ..."
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null && curl -sf http://127.0.0.1:3100/health >/dev/null && curl -sf http://127.0.0.1:3000/ >/dev/null; then
    echo "READY"
    curl -s http://127.0.0.1:8000/health | python3 -m json.tool | head -35
    echo
    echo "Dashboard  http://127.0.0.1:3000"
    echo "API        http://127.0.0.1:8000/docs"
    echo "Remotion   http://127.0.0.1:3100/health"
    echo "Logs       $ROOT/logs/"
    exit 0
  fi
  sleep 1
done
echo "Timed out waiting for services — check logs/"
exit 1
