Feature                         Status
------------------------------------------------
Campaign discovery             ✅  (hardened extension selectors + ingest API; no unattended bot)
Campaign scoring               ✅  (CampaignScoringService + learning priors on ingest)
Requirement extraction         ✅  (parser + brief extractor)
Asset importing                ✅  (type/size/sanitize upload; extension lists download URLs)
WhisperX + CUDA                ✅  (torch 2.11+cu128 on RTX 5060; Silero VAD; diarization optional)
Scene detection                ✅  (PySceneDetect when installed; window fallback)
AI clip ranking                ✅  (ClipRankingService; top 3–5 only rendered)
3-account variations           ✅  (round-robin distinct candidates + style captions)
Rendering                      ✅  (FFmpeg base cut + Remotion overlay service writes real mp4)
Compliance                     ✅  (honest unverified logo/CTA/video-disclosure flags)
Approval queue                 ✅  (in-app video preview + score/compliance/regenerate)
Posting assistant              ✅  (copy caption / open TikTok / mark posted — no auto-post)
Submission assistant           ✅  (highlight Submit + clipboard/package soft-prefill; no auto-click)
Analytics                      ✅  (views from clip_performance; cohorts)
Learning engine                ✅  (priors feed discover ranking when history exists)
Earnings tracker               ✅
Payout notifications           ✅
£1K dashboard + forecast       ✅
Media preview API              ✅  (/api/media/* auth-gated)
Secrets / prod gate            ✅  (rotate_secrets.py + CLIPOPS_ENV=production refuses weak JWT/password)
Tests                          ✅  (unit suite in tests/test_core.py)
