# ClipOps — Operator Mode

Approve → post → submit → cash out. ~85–90% automated without Content Rewards / TikTok posting bots.

## What it does

```
Content Rewards (your logged-in browser)
        ↓ extension scans
Campaign scorer AI (top 3)
        ↓ YOU approve
Clip generator (WhisperX → scenes → rank)
        ↓ 10–20 candidates → best 3–5
3 account assignments (not 3 clones of every clip)
        ↓ compliance
YOU approve videos
        ↓ posting packages
YOU confirm TikTok Post
        ↓ submission assist
YOU confirm CR Submit
        ↓ analytics + learning records
Payout notification → YOU confirm cash-out
```

## Quick start

```powershell
# 1) Secrets (required after first clone / for prod)
cd clipops
.\apps\api\.venv\Scripts\python.exe scripts\rotate_secrets.py --print-password

# 2) API
cd apps\api
.\.venv\Scripts\activate
$env:PYTHONPATH="..\..\..;$PWD"
uvicorn app.main:app --reload --port 8000

# 3) Remotion caption burn-in (separate terminal)
cd ..\..\templates
npm install
npm start

# 4) Dashboard
cd ..\apps\dashboard
npm install
npm run dev
```

Login: `operator@clipops.local` + the password printed by `rotate_secrets.py`  
(Demo plaintext `changeme` only works if you have not rotated yet.)  
See [docs/SECRETS.md](docs/SECRETS.md). Production: `--production` refuses weak JWT/password at startup.

## GPU / WhisperX (RTX 50-series)

```powershell
.\apps\api\.venv\Scripts\python.exe scripts\install_whisperx_cuda.py
```

Installs **PyTorch cu128** (Blackwell / RTX 5060) + WhisperX. Transcription order: WhisperX (Silero VAD) → faster-whisper → heuristic. Scene cuts: PySceneDetect → fixed windows.

## Remotion

`templates/` runs a real render service on `:3100`. FFmpeg still cuts 9:16; Remotion overlays animated hooks and returns `rendered_path` for the export package.

## Manual gates (never automated)

1. Approve campaign (+ your Join click on CR)  
2. Confirm TikTok Post  
3. Confirm Content Rewards Submit  
4. Confirm cash-out  

## Repo layout

- `apps/dashboard` — Next.js Operator UI  
- `apps/api` — FastAPI  
- `browser-extension` — CR session assist (no auto-click)  
- `templates/` — Remotion render service  
- `workers/` — WhisperX, scenes, ranking, captions, FFmpeg  
- `scripts/` — `rotate_secrets.py`, `install_whisperx_cuda.py`  
