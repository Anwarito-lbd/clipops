---
tags:
  - architecture
---

# Operator Studio UI & CLI

Connects: [[Home]], [[Ingest]], [[Transcription]], [[SceneDetection]], [[Scoring]], [[RetentionPacing]], [[Hooks]], [[Editing]], [[Remotion]], [[Export]]

Implemented in `apps/operator-ui/studio.py`, `apps/operator-ui/server.py`, `apps/operator-ui/cli.py`, and `apps/operator-ui/static/`.

## Lightweight Local Studio UI

Run with `.venv/Scripts/python.exe apps/operator-ui/cli.py serve --port 8010` (no Postgres, Redis, or Next.js build required).

- **Step-by-Step Pipeline Bar**: Trigger `Probe`, `WhisperX / ASR`, `PySceneDetect` (`content` / `adaptive` / `hybrid`), `Hook & Pacing`, and `FFmpeg Render` individually or via one-click `+ Run 24s Demo`.
- **Interactive Cut & Scene Timeline**: Inspect detected cut boundaries proportionally, preview both source footage and rendered `9:16` MP4 cuts in `<video>`, and tune `start_sec`, `end_sec`, `style`, `duration_band`, and `hook_text`.
- **Dry-Run Filtergraph Inspector**: Calls `build_filtergraph` via `POST /api/studio/sessions/{id}/clips/{clip_id}/dry-run` to inspect the exact `-vf`, `-af`, resolved system `fontfile`, CLI command, Remotion payload, and 12-point compliance gate before writing video bytes.
- **Human Approval Gate**: Operators explicitly click **Approve Cut** or **Reject Cut**; ClipOps never auto-posts.

## CLI Commands (`apps/operator-ui/cli.py`)

- `health` · `probe <video>` · `transcribe <video>` · `scenes <video> --detector hybrid` · `score <video>` · `dry-run <video>` · `render <video>` · `demo` · `serve`

See [[EXAMPLES]] for verified CLI and Studio UI outputs.
