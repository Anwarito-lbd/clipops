Feature                         Status
------------------------------------------------
Campaign discovery             ✅  (hardened extension selectors + ingest API; no unattended bot)
Campaign scoring               ✅  (CampaignScoringService + learning priors on ingest)
Requirement extraction         ✅  (parser + brief extractor)
Asset importing                ✅  (type/size/sanitize; CELERY_EAGER inline by default)
WhisperX + CUDA                ✅  (Silero VAD; engine surfaced on asset)
Scene detection                ✅
AI clip ranking                ✅  (heuristic ranking; top 3–5 draft-rendered)
3-account variations           ✅
Draft render before approve    ✅  (Review preview uses DRAFT package)
Rendering                      ✅  (FFmpeg + optional Remotion)
Compliance                     ✅
Approval queue                 ✅  (preview → approve promotes draft to EXPORTED)
Posting / exports              ✅  (Download video via /api/media)
Submission assistant           ✅  (popup package assist + Submit highlight)
State transitions              ✅  (approve/reject/posted/submitted/regenerate)
Secrets / prod gate            ✅
Tests                          ✅  (unit + smoke pipeline)
£1K dashboard + learning       ✅
