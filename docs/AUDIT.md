# ClipOps audit (updated 2026-07-27)

Supersedes earlier gap list. Current status is tracked in `IMPLEMENTATION_STATUS.md`.

## Closed since last audit

- WhisperX + CUDA 12.8 (RTX 5060 / Blackwell) via `scripts/install_whisperx_cuda.py`; Silero VAD
- Remotion `/render` writes real mp4 overlays (HTTP local-file proxy)
- Secrets rotation (`scripts/rotate_secrets.py`) + production boot refuse weak JWT/password
- Upload allowlist/sanitize; media preview API; honest compliance unverified flags
- Learning priors on discover; extension scanner harden; submission package assist

## Still optional / ops notes

- Pyannote diarization needs HF token + working torchcodec shared FFmpeg DLLs on Windows — ASR works without it
- Remotion must be running on `:3100` for animated overlays (FFmpeg drawtext still burns hooks if Remotion is down)
- JWT in browser `localStorage` / extension storage — fine for single-operator local; use HTTPS + short TTL for shared deploy
- n8n workflow remains optional glue, not required for Operator Mode

## Non-goals (unchanged)

No auto Join / Post / Submit / Cash-out, no CAPTCHA bypass, no engagement bots.
