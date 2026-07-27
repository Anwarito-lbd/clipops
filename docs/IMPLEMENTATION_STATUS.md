Feature                         Status
------------------------------------------------
Campaign discovery             ✅  (hardened extension selectors + ingest API; no unattended bot)
Campaign scoring               ✅  (CampaignScoringService + learning priors on ingest)
Requirement extraction         ✅  (parser + brief extractor)
Asset importing                ✅  (type/size/sanitize; CELERY_EAGER inline by default)
WhisperX + CUDA                ✅  (ffmpeg wav extract; Silero VAD; optional HF diarization)
Scene detection                ✅
Draft render before approve    ✅
Rendering                      ✅  (FFmpeg + Remotion :3100)
Redis / Celery async           ✅  (Redis installed; eager default; worker script for async)
Ops scripts                    ✅  (start_stack / start_remotion / start_celery_worker)
Stack readiness UI             ✅  (Home + /health media.readiness_pct)
Secrets / prod gate            ✅
Tests                          ✅
Month-1 readiness              ✅  (~90% — see docs/READINESS.md)
