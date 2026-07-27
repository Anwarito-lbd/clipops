# ClipOps readiness — how to reach **99%**

## Two different scores

| Score | What it measures | Your machine now |
|-------|------------------|------------------|
| **Stack** (`/health` media) | GPU, FFmpeg, Remotion, Redis, ASR | Already **~100%** |
| **Go-live** (`/api/operator/readiness`) | Software + one full human dry run | Climbs as you complete the loop |

**99% = go-live score**, not stack. The last points only come from *you* doing CR/TikTok clicks once.

## Path to 99% (in order)

1. **Start stack** — `.\scripts\go_live_99.ps1` (or `start_stack.ps1`)
2. **API + dashboard** — see README; sign in with rotated password
3. **Chrome extension** — Load unpacked `browser-extension/`
4. **Scan CR** — logged-in Content Rewards tab → Scan → Approve campaign → **you Join**
5. **Upload footage** — Assets → wait until GENERATED / drafts ready
6. **Review** — preview draft → Approve → Exports → **Download**
7. **You Post on TikTok** → paste URL → Mark posted  
8. **You Submit on CR** (extension can highlight) → Mark submitted  
9. **Enter views** in Tracking after a day — learning loop closes  

Home shows **Go-live score** and the next 3 incomplete steps automatically.

## What will never be 100% in this product

- Auto Join / Post / Submit / Cash-out (forbidden by design)
- Guaranteed £1K (planning target only)
- Perfect CR DOM scraping if their site redesigns (extension may need selector tweaks)

## Optional polish (not required for 99%)

- `HF_TOKEN` — speaker diarization  
- `CELERY_EAGER=false` + worker — async long videos  
- `CLIPOPS_ENV=production` — if the machine is shared/remote  

## Day-1 commands

```powershell
.\scripts\go_live_99.ps1
# then API + dashboard from README
```
