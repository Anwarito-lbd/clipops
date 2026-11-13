---
tags:
  - config
---

# Models, Presets & Schemas

Referenced by [[Transcription]], [[Editing]], [[Remotion]], [[Config]], [[EXAMPLES]]. Back to [[Home]].

None of the ranking or hook scoring math calls an external LLM. "Model" in ClipOps refers to ASR checkpoints, editorial style presets, and database schemas.

## Speech Recognition Checkpoints

- `workers/transcription/transcribe.py` passes `WHISPERX_MODEL` through to WhisperX (`wav2vec2` phoneme alignment + Silero VAD) or `faster-whisper` (`tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`; unknown names normalize to `medium`).
- Diarization uses `whisperx.DiarizationPipeline` only when `HF_TOKEN` is configured.
- The heuristic fallback loads zero weights and maps five timed anchor lines across the probed duration so silent/tone test fixtures still exercise [[Scoring]] and [[RetentionPacing]].

## Editorial Style Presets

`ACCOUNT_STYLES = ["dramatic", "educational", "commentary"]` (`packages/shared_types/constants.py`) map 1:1 to FFmpeg zoom/overlay geometries in [[Editing]] and React compositions in [[Remotion]].

## Database & Forecast Constants

- `apps/api/app/db.py` defines SQLAlchemy models (`SocialAccount`, `Campaign`, `CampaignRequirement`, `SourceAsset`, `ClipCandidate`, `ClipVersion`, `Render`, `ComplianceCheck`, `DiscoveredCampaign`, `ClipPerformance`, `ProductionEvent`).
- `ForecastService.forecast` (`packages/services/forecast.py`) uses explicit planning defaults (`avg_views_per_clip=8210.0`, `planning_cpm=2.0`, `approval_rate=0.7`) when performance rows are empty — clearly labeled as planning assumptions, never fabricated metrics.
