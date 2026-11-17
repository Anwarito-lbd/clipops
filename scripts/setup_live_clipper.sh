#!/usr/bin/env bash
# ClipOps live clipper + auto-poster setup (macOS / Linux)
#   bash scripts/setup_live_clipper.sh            WHISPER_MODELS="tiny,small" PYTHON=python3.12
set -euo pipefail
cd "$(dirname "$0")/.."
WHISPER_MODELS="${WHISPER_MODELS:-tiny,small}"
PYTHON="${PYTHON:-python3}"
step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }

step "Python virtual environment (.venv)"
[ -x .venv/bin/python ] || "$PYTHON" -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install -q --upgrade pip wheel

step "Python packages (streamlink, faster-whisper, Google OAuth, API stack)"
"$PY" -m pip install -r apps/api/requirements.txt
"$PY" -m pip install "streamlink>=6.0" "faster-whisper>=1.0.0" "google-auth-oauthlib>=1.2" "python-dotenv>=1.0"

step "FFmpeg (with libass for burned captions)"
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then brew install ffmpeg
  elif command -v apt-get >/dev/null; then sudo apt-get install -y ffmpeg
  else echo "install ffmpeg (with libass) and re-run"; fi
else echo "ffmpeg found: $(command -v ffmpeg)"; fi

step "Pre-download Whisper models ($WHISPER_MODELS)"
IFS=',' read -ra MODELS <<< "$WHISPER_MODELS"
for m in "${MODELS[@]}"; do
  "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('${m// /}', device='cpu', compute_type='int8'); print('whisper ${m// /} ready')" \
    || echo "WARN: could not download whisper ${m// /} (network?) — re-run this script before launch"
done

step "Config files"
mkdir -p secrets && chmod 700 secrets
[ -f .env ] || { cp .env.example .env; echo "created .env -> fill in the keys"; }
[ -f accounts.json ] || { cp workers/publisher/accounts.example.json accounts.json; echo "created accounts.json -> review it"; }

step "Self-check"
"$PY" -m workers.publisher doctor --accounts accounts.json || true
printf '\nNext: fill .env, run the auth commands doctor lists, then:\n'
echo "  $PY -m workers.live_clipper live --wave au --scout 3 --language en --profile gta6 --layout split --streamers workers/live_clipper/gta6_streamers.json --autopost accounts.json --autopost-dry-run"
