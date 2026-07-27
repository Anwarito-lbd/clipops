# Optional stack: Redis async workers, Remotion, diarization

## Modes

| Mode | When | Config |
|------|------|--------|
| **Eager (default)** | Solo laptop, simplest | `CELERY_EAGER=true` — pipeline runs inside API process |
| **Async** | Long videos / keep API snappy | Redis + `CELERY_EAGER=false` + Celery worker |

## Start helpers (Windows)

```powershell
# Redis + Remotion windows
.\scripts\start_stack.ps1

# Celery worker (async mode)
.\scripts\start_celery_worker.ps1

# Remotion only
.\scripts\start_remotion.ps1
```

Redis was installable via `winget install Redis.Redis`. Default port **6379**.

## Diarization (optional)

1. Create a Hugging Face token with access to `pyannote/speaker-diarization-community-1` (accept model terms).
2. Set in `.env`:

```
HF_TOKEN=hf_...
ENABLE_DIARIZATION=true
```

ASR works without this (Silero VAD + WhisperX/faster-whisper). Diarization only adds speaker labels.

## Remotion

Must listen on `REMOTION_URL` (default `http://127.0.0.1:3100`) for animated overlays. If down, FFmpeg still burns hook text into the cut.

## Health

`GET /health` → `media.readiness_pct`, `remotion`, `redis`, `celery_eager`, `diarization_ready`.
