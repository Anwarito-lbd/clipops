# Content Rewards linking + Scrapling discovery

## How to link your Content Rewards account

ClipOps **never** stores your CR password and **never** auto-Joins or cash-outs.

1. Start the API (`:8000`) and log into the dashboard.
2. Chrome → `chrome://extensions` → Load unpacked → `browser-extension/`.
3. Extension Options → paste your ClipOps JWT (from dashboard login).
4. Open Content Rewards **while logged in** → popup → **Scan campaigns**.
5. Campaigns land in Operator Mode, ranked. Click **Approve Campaign**.
6. ClipOps creates a **JOIN NOW** notification — **you** click Join on CR.

## Scrapling public discover ([D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling))

`POST /api/operator/discover/scrapling` (or Operator UI **Pull campaigns**) scrapes the **public** discover board with Scrapling's HTTP `Fetcher` (not StealthyFetcher CAPTCHA bypass).

- Results go through the same ranker as the extension.
- Whop ToS disallow scraping without written consent — use at your own risk.
- Bot **cannot** Join (`bot_can_join: false`).

## Notifications you act on

| Kind | Meaning | Bot can do it? |
|------|---------|----------------|
| `join_now` | Approved campaign — open CR and Join | **No** |
| `cashout_now` | Payout ready — open cash-out | **No** |
| `discover_ready` | Scrapling/extension ranked campaigns | N/A |

## Video pipeline (not MoneyPrinterTurbo)

Campaign footage → Whisper → scenes → rank → FFmpeg 9:16 + Remotion karaoke subtitles.

Optional: `ENABLE_TTS_COMMENTARY=true` adds Edge-TTS voiceover for the **commentary** account only, mixed onto the **same campaign cut** (no Pexels stock replacement).
