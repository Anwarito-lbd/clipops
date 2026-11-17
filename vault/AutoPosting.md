---
tags:
  - pipeline
  - live
---

# Auto-Posting (YouTube · TikTok · Instagram)

Upstream: [[LiveClipping]] (leaderboard) · Strategy: [[GTA6]] · Copy rules: [[Hooks]] · Replaces the manual step in [[Export]]

Implemented in `workers/publisher/`. **Opt-in.** Without `--autopost`, ClipOps still stops at review and you post by hand.

## Flow

`leaderboard.json` → `plan_posts` (two lanes) → gates → publish → `posted.json` + `autopost_log.jsonl` + Discord ping

| Lane | Account | Takes | Media |
| --- | --- | --- | --- |
| FIRST | A | best clip of each **fresh** moment (≤ 15 min old), score ≥ 60 | captioned final (default) or draft (`"first_lane_media": "draft"`) |
| BEST | B | everything else ≥ 45: stale moments, other streamers' reactions, rotating streamer + moment type | captioned final |

The same clip is never posted to both accounts, and byte-identical videos are refused by SHA-256.

## Safety Gates (in order)

1. Hold list: `python -m workers.publisher hold <session> <clip_id>`.
2. Veto window: `veto_seconds` (default 45 s). A Discord ping announces every queued post so you can hold it from your phone.
3. Duplicate check: file hash.
4. **Grok writes the copy**: title, hook, caption, TikTok caption, YouTube title with #Shorts. It falls back to the clipper's post kit.
5. **Grok safety review** of the transcript, chat and copy. It holds on slurs or hate, sexual content, doxxing or private info, minors, graphic real violence, story spoilers, or misleading titles. With `require_review: true`, a missing or unreachable Grok means **hold**, not post.
6. Quotas: `per_account_per_day` (10). Instagram also caps API publishing at 50 per 24 h.

## Platform Reality (checked Nov 2026)

| Platform | Official API | Public on launch day? |
| --- | --- | --- |
| YouTube | Data API v3 resumable upload | ❌ Unaudited projects are **locked to private**. Audit via the "YouTube API Services – Audit and Quota Extension Form". |
| TikTok | Content Posting API (Direct Post) | ❌ Unaudited apps post **SELF_ONLY**, the account must be private, max 5 users / 24 h. |
| Instagram | Graph API Reels (resumable via rupload.facebook.com) | ✅ Your own Business/Creator account works with the Meta app in Development mode. |
| All three | **Ayrshare** (`"via": "ayrshare"`) | ✅ Uses Ayrshare's already-audited apps (paid). Verify with one test post first. |

So the launch config (`workers/publisher/accounts.example.json`) routes YouTube and TikTok through Ayrshare and Instagram through the official API. Switch each to `"via": "official"` once your audits pass.

## Launch Checklist

1. `scripts/setup_live_clipper.ps1` (Windows) or `.sh`: venv, packages, ffmpeg, Whisper models, `.env`, `accounts.json`, then `doctor`.
2. Keys in `.env`: `TWITCH_*`, `XAI_API_KEY`, `AYRSHARE_API_KEY` + profile keys, `META_APP_*`, `DISCORD_WEBHOOK_URL`.
3. `python -m workers.publisher auth instagram --account A --short-token …` (and B).
4. `python -m workers.publisher grok-test`: confirms the model, caption and review.
5. **One real test post per account** to a throwaway or private profile: `python -m workers.publisher post <clip_dir> --account A`.
6. Rehearse with `--autopost accounts.json --autopost-dry-run` on a live channel. Then drop `--autopost-dry-run`.

Back to [[Home]].
