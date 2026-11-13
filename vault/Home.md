---
tags:
  - index
---

# ClipOps clipping brain

This vault is a map of the clipping pipeline in this repository. Every note links to a real module. Numbers in [[EXAMPLES]] come from commands and HTTP calls run against this tree, not from a target deck.

ClipOps helps one operator turn a Content Rewards brief and a source video into a few different 9:16 packages. Join, TikTok post, Content Rewards submit, and cash-out stay manual. The API states that boundary as `automation_boundary: human_approval_manual_posting` on `GET /health`.

## Pipeline

1. [[Ingest]] — extension scan or upload, then a campaign row and a source file
2. [[Transcription]] — WhisperX, then faster-whisper, then a heuristic transcript
3. [[Scoring]] — campaign score, then clip rank
4. [[Hooks]] — hook words and per-account caption copy
5. [[Editing]] — FFmpeg 9:16 cut, optional Remotion overlay
6. [[Export]] — compliance, review, and the manual post

## Reference

- [[Config]] — settings, eager Celery, storage
- [[Models]] — ASR model names, account styles, database rows
- [[EXAMPLES]] — the offline demo and the local API session

Open this folder as an Obsidian vault and start here. The graph colors are index, pipeline, examples, and config.
