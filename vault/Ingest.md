---
tags:
  - pipeline
---

# Ingest & Brief Parsing

Downstream: [[Transcription]], [[SceneDetection]] · Settings: [[Config]] · Interactive UI: [[OperatorUI]]

Two entry points feed source media into the workstation:

1. **Operator Studio Local File / Demo Synthesizer (`apps/operator-ui/studio.py`)** — probes local `.mp4`/`.mov`/`.webm` via `ffprobe` or generates a synthetic 3-scene `1080×1920` H.264 demo reel (`synthesize_demo_video`) for offline testing.
2. **API Upload (`POST /api/campaigns/{id}/assets` in `apps/api/app/routers/pipeline.py`)** — streams uploads in 1 MiB chunks, enforces `MAX_UPLOAD_MB`, validates MIME/extension via `assert_allowed_upload`, sanitizes filenames (`sanitize_filename`), hashes content with SHA-256, and queues `process_asset`.

Briefs are parsed deterministically by `parse_campaign_brief` (`packages/campaign_parser/parser.py`) to extract CPM, budget, target geography, duration bounds, disclosure string, and required hashtags before [[Scoring]] evaluates eligibility.

Next: [[Transcription]] and [[SceneDetection]].
