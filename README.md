# ClipOps — Operator Mode

Approve → post → submit → cash out. ~85–90% automated without Content Rewards / TikTok posting bots.

## What it does

```
Content Rewards (your logged-in browser)
        ↓ extension scans
Campaign scorer AI (top 3)
        ↓ YOU approve
Clip generator (WhisperX → scenes → rank)
        ↓ 10–20 candidates → best 3–5
3 account assignments (not 3 clones of every clip)
        ↓ compliance
YOU approve videos
        ↓ posting packages
YOU confirm TikTok Post
        ↓ submission assist
YOU confirm CR Submit
        ↓ analytics + learning records
Payout notification → YOU confirm cash-out
```

## Clip selection (updated)

1. Generate **10–20** candidate clips  
2. AI ranks them  
3. Take best **3–5**  
4. Assign round-robin to TikTok accounts (dramatic / educational / commentary)  

## Learning

Every posted clip stores: campaign, account, hook type, length, style, caption style, posting time, views, engagement, approval, verified views, earnings.

After ~50–100 clips, `/api/operator/learning` recommends what to produce more of.

## Quick start

```powershell
cd clipops\apps\api
.\.venv\Scripts\activate
$env:PYTHONPATH="..\..\..;$PWD"
uvicorn app.main:app --reload --port 8000

cd ..\dashboard
npm install
npm run dev
```

Login: `operator@clipops.local` / `changeme`

- Home: http://localhost:3000  
- API docs: http://127.0.0.1:8000/docs  
- Extension: load `browser-extension/` unpacked (see its README)

## Manual gates (never automated)

1. Approve campaign (+ your Join click on CR)  
2. Confirm TikTok Post  
3. Confirm Content Rewards Submit  
4. Confirm cash-out  

Unattended Playwright against Content Rewards is **not** included — only enable with written CR permission.

## Repo layout

- `apps/dashboard` — Next.js Operator UI ($1K home, queue, learning)  
- `apps/api` — FastAPI  
- `browser-extension` — CR session scanner / brief / assets / submit highlight / payout watch  
- `packages/campaign_engine` — ranking + EV  
- `packages/posting_queue` — account router  
- `packages/analytics` — performance + learning  
- `workers/` — WhisperX, scenes, ranking, captions, FFmpeg render  
- `templates/` — Remotion styles  
