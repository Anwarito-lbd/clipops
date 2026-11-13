---
tags:
  - index
---

# ClipOps Clipping Brain

This Obsidian vault is an interconnected technical map of **ClipOps**, an ethical short-form video clipping & editing workstation. Every note links directly to real modules in this repository, and all benchmark numbers in [[EXAMPLES]] come from observed local runs.

ClipOps stops strictly at human approval and manual export: `automation_boundary: human_approval_manual_publish` (no auto-posting, no bot farming, no platform spam).

## Pipeline Stages

1. [[Ingest]] — source video upload, filename sanitization, brief parsing (`apps/api/app/routers/pipeline.py`)
2. [[Transcription]] — WhisperX forced-alignment word timestamps, Silero VAD, `faster-whisper` PCM fallback (`workers/transcription/transcribe.py`)
3. [[SceneDetection]] — PySceneDetect `ContentDetector` & `AdaptiveDetector` cut boundaries (`workers/scene_detection/detect.py`)
4. [[Scoring]] — deterministic campaign & clip candidate ranking (`packages/services/clip_ranking.py`)
5. [[Hooks]] — hook taxonomy, opening-line weighting, and editorial style copy (`workers/clip_ranking/hooks.py`)
6. [[RetentionPacing]] — WPM speaking rate, 3-second hook density, and dead-air penalty math (`packages/services/clip_ranking.py`)
7. [[Editing]] — FFmpeg 9:16 filtergraphs, cross-platform `fontfile` resolution, EBU R128 loudness (`workers/video_rendering/render.py`)
8. [[Remotion]] — optional React/Remotion 4.0 caption compositing service (`templates/server.js`)
9. [[Export]] — 12-point compliance gate, SHA-256 duplicate prevention, and manual publish workflow (`packages/compliance_checker/checker.py`)

## Workstation & Operations

- [[OperatorUI]] — lightweight local FastAPI Studio UI & CLI for step-by-step inspection and dry-run renders (`apps/operator-ui/server.py`, `apps/operator-ui/cli.py`)
- [[Config]] — environment configuration, eager Celery mode, and production secret audit (`apps/api/app/config.py`)
- [[Models]] — ASR checkpoints, editorial styles (`dramatic`, `educational`, `commentary`), and SQLAlchemy schemas (`apps/api/app/db.py`)
- [[EXAMPLES]] — verified CLI, offline demo, Operator Studio, and pytest outputs (`docs/PROOF_OF_WORK.md`)

Open `vault/` in Obsidian with Graph View enabled. Every note has incoming and outgoing wikilinks (**zero orphan notes**).
