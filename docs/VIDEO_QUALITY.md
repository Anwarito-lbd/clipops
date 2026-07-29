# Video quality notes

## What ClipOps does

Best-effort **campaign clips** from authorized footage:

1. Transcribe (WhisperX / faster-whisper)
2. Scene detect + rank 10–20 candidates
3. Assign top clips across linked TikTok + YouTube accounts
4. FFmpeg 9:16 cut + **stronger subtitle styles** (Remotion karaoke word-highlight)
5. Optional **Edge TTS commentary** for the commentary account (mixed onto the cut)

## What we borrowed from MoneyPrinterTurbo

| Feature | In ClipOps |
|---------|------------|
| Strong outline / karaoke subtitles | Yes — Remotion `StyleOverlay` + FFmpeg fallback |
| Edge TTS voiceover | Yes — commentary style only (`ENABLE_TTS_COMMENTARY`) |
| LLM script + Pexels stock | **No** — CR campaigns require brand footage |

Repo: https://github.com/harry0703/MoneyPrinterTurbo

## Enable TTS commentary

```bash
# .env
ENABLE_TTS_COMMENTARY=true
TTS_VOICE=en-US-JennyNeural
```

```bash
apps/api/.venv/bin/pip install edge-tts
```

Restart the API. Re-process an asset; commentary-account packages get `commentary_tts.mp3` mixed under original audio.
