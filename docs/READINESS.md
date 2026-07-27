# ClipOps readiness (2026-07-27)

## Score: **~90% ready for month-1 Operator Mode**

You can run the full human-gated loop on this machine today.

| Area | Ready? | Notes |
|------|--------|-------|
| Campaign discover → approve → Join (you) | Yes | Extension + Operator UI |
| Upload → ASR → scenes → rank → draft render | Yes | CUDA WhisperX/faster-whisper; eager pipeline default |
| Preview → approve → export download | Yes | Review + Exports |
| Post / Submit / Cash-out | Assist only | You click; ClipOps never auto-clicks |
| Tracking / £1K forecast / learning | Yes | Needs real post metrics over time |
| Secrets | Yes locally | Rotated hash+JWT; set `CLIPOPS_ENV=production` for shared host |
| Remotion overlays | Yes if `:3100` up | Else FFmpeg hook burn-in |
| Redis async workers | Optional | Installed + pingable; keep `CELERY_EAGER=true` unless you want async |
| Speaker diarization | Optional | Needs `HF_TOKEN` + pyannote model access |

## What “ready” means here

- **Software:** Operator Mode path is implemented and smoke-tested.
- **Earnings:** £1K is a **planning target**, not guaranteed — depends on CR campaigns, CPM, approval rate, and your posting volume.
- **Still human:** Join, TikTok Post, CR Submit, Cash-out stay manual by design.

## Day-1 checklist

1. `.\scripts\start_stack.ps1` (Redis + Remotion)
2. API + dashboard (see README)
3. Sign in with rotated password
4. Load extension → scan CR → approve campaign → Join yourself
5. Upload footage → Review drafts → Approve → Download → Post yourself
