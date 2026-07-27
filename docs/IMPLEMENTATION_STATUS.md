Feature                         Status
------------------------------------------------
Campaign discovery             ⚠️  (browser-assisted extension + ingest API; no unattended bot)
Campaign scoring               ✅  (CampaignScoringService + explanations + recommendation)
Requirement extraction         ✅  (parser + brief extractor)
Asset importing                ✅  (upload API; extension lists download URLs)
WhisperX                       ⚠️  (optional; heuristic fallback if not installed)
Scene detection                ⚠️  (PySceneDetect optional; window fallback)
AI clip ranking                ✅  (ClipRankingService richer heuristics; top 3–5 only rendered)
3-account variations           ✅  (round-robin distinct candidates + style captions)
Rendering                      ⚠️  (FFmpeg working when installed; Remotion burn-in still stub)
Compliance                     ✅  (checklist + requirement snapshots)
Approval queue                 ✅  (score/compliance/regenerate/open links)
Posting assistant              ✅  (copy caption / open TikTok / mark posted — no auto-post)
Submission assistant           ⚠️  (highlight Submit + mark submitted; no CR form prefill)
Analytics                      ✅  (views from clip_performance; cohorts)
Learning engine                ✅  (PerformanceLearningService; closed-loop blend when history exists)
Earnings tracker               ✅
Payout notifications           ✅
£1K dashboard + forecast       ✅  (GBP target + run-rate / required clips/day)
Tests                          ✅  (unit suite in tests/test_core.py)
Security audit                 ⚠️  (documented; harden secrets/uploads before production)
