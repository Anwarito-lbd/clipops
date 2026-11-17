---
tags:
  - playbook
  - gta6
---

# GTA 6 Launch Clipping Playbook

Engine: [[LiveClipping]] · Moment taxonomy: [[GTA6Moments]] · Captions: [[Transcription]] · Layout: [[Editing]] · Rules: [[Export]]

Profile: `--profile gta6` (`workers/live_clipper/profiles.py`).

## Game Facts (verify before launch)

- **Grand Theft Auto VI**, Rockstar Games (Take-Two). Set in the state of **Leonida**, centred on **Vice City**.
- Protagonists **Lucia** and **Jason** — their names are in the Whisper vocabulary prompt so captions spell them right.
- Consoles at launch: PS5 and Xbox Series X|S.
- Release date was moved twice (2025 → May 26 2026 → **November 19 2026**). Rockstar: **midnight local time**. US stores key to Eastern time, so the US unlock is **12:00 AM ET Nov 19 = 9:00 PM PT Nov 18**. New Zealand unlocks first. No PC version at launch.

## Two Waves: Australia First, Then the US

Rockstar unlocks at **midnight local time**, so New Zealand and Australia play **12–18 hours before the US**:

| Wave | Unlock | ET equivalent | Channels (`workers/live_clipper/gta6_streamers.json`) |
| --- | --- | --- | --- |
| `au` | midnight AEDT / NZDT, Nov 19 | ~6 AM (NZ) to 8 AM (AU) ET, **Nov 18** | DarkViperAU (Australian GTA speedrunner, launch stream), HeyImZed, plus `--scout` |
| `us` | midnight ET, Nov 19 | Kai live 8 PM ET Nov 18, Speed 9 PM ET | kaicenat, ishowspeed, lacy, clix, marlon, jasontheween, stableronaldo |

**The AU wave is your best shot at being first.** Every "first time" moment (first car, first wanted level, first look at Vice City) happens there half a day before US streamers reach it. Most English clip pages are asleep or waiting for Kai. Post the best AU moments on account A (FIRST lane) before the US wave starts.

- During the AU wave, `--scout` mostly surfaces AU/NZ channels, since they're the only ones legitimately playing.
- **Skip streamers using the "New Zealand time-zone trick"** to unlock early on Xbox. A streamer was reportedly warned about a ban for it, and clips of a stream that gets struck can be taken down with it. Clip genuine AU/NZ streamers.
- Reports conflict on whether Rockstar set a streaming embargo tied to the first unlock, so check Rockstar's channels on the morning.

## Who To Clip (announced as of Nov 16–17 2026; re-check on the night)

| Streamer | Platform | Plan | Clipper support |
| --- | --- | --- | --- |
| Kai Cenat | Twitch (+ YouTube) | Full playthrough, live **Nov 18, 8 PM EST** | ✅ Twitch chat |
| IShowSpeed | YouTube + Twitch | First stream **Nov 18, 9 PM EST**, then 10–12 h/day | ✅ via his Twitch |
| Lacy + Clix, Marlon, JasonTheWeen, Stable Ronaldo | mostly Twitch | Week-long 24/7 marathon | ✅ |
| Ahgren, Michou | Twitch | Non-stop / marathon streams | ✅ |
| YouTube official 24 h event (RDCWorld pre-show) | YouTube | Nov 18 11 PM ET → 24 h | ❌ no YouTube chat yet |
| Kick streamers | Kick | unconfirmed | ❌ no Kick chat yet |

Don't hard-code the list: `python -m workers.live_clipper scout` shows who is actually live in the **Grand Theft Auto VI** category by viewers, and `live --scout 5` auto-picks the top channels. Mix **2 mega streamers** (biggest moments, most competition) with **2–3 mid-size marathon streamers**. Fewer clippers watch those, so you're more often first, and marathons keep producing moments after the big names log off.

## Two Accounts, 20 Posts a Day

Fully automatic with `--autopost accounts.json`. Gates, Grok review and which platforms can post publicly on launch day: [[AutoPosting]].

`python -m workers.live_clipper plan <session>` splits the leaderboard into two lanes (`workers/live_clipper/planner.py`):

- **Account A, FIRST lane (10/day):** the single best clip of each moment across all streamers, posted as the **draft** as soon as it scores ≥ 60. When five streamers hit the same moment, only the best one goes here.
- **Account B, BEST lane (10/day):** captioned finals, highest score first, rotating streamer and moment type. It picks up other streamers' reactions to moments A already covered. That's different content, riding the same hype.
- **Never upload the same clip to both accounts.** Platforms suppress duplicate uploads, and the [[Export]] gate rejects identical versions. Volume works when every post is distinct.
- Front-load the quota: the first **48–72 h** after unlock are the peak. Spend more of each day's quota during launch-night hours, not evenly.
- After posting, log it with `plan <session> --mark <clip_id> --account A` so quotas and duplicate checks stay correct.

## Why Launch Night Is Different

- Every big streamer plays the **same first hours**, so each moment type (first wanted level, first crash, first look at Vice City) gets clipped many times. **The first good post of each moment wins.** That is why the clipper fires mid-bucket and ships a draft first.
- Chats are huge and already loud, so they can't jump 2.5× like a small chat. The profile lowers `ratio` to 2.0 and raises `min_msgs` to 15. The Poisson + z-score tests still stop noise.
- Slow mode, emote-only or sub-only mode flattens the chat signal. If a channel goes quiet in the leaderboard, run `spikes` on its `chat.jsonl` and lower `--ratio` for that channel.

## Run Sheet

1. **Day before:** `pip install streamlink faster-whisper`. Run any command once with captions on so the Whisper model downloads ahead of time. Test against one live channel for 10 minutes.
2. **Build `streamers.json`** with each streamer's facecam box (x, y, w, h as fractions of the frame) so `--layout split` puts their face on top and gameplay below. Reaction-led clips perform best and are the safest to post.
3. **Pick 3–6 channels** (`scout`) you can actually review. Recording is cheap (stream copy); rendering and Whisper aren't. On a GPU use `--device cuda --model small`.
4. **Measure facecams** once each stream is live: `python -m workers.live_clipper snapshot darkviperau kaicenat …`. Read each box off the yellow 10 % grid into `"facecam": [x, y, w, h]` in `gta6_streamers.json`.
5. **AU wave (≈6–8 AM ET Nov 18):** `python -m workers.live_clipper live --wave au --scout 3 --language en --profile gta6 --layout split --streamers workers/live_clipper/gta6_streamers.json`
6. **US wave (from 8 PM ET Nov 18):** `python -m workers.live_clipper live --wave us --profile gta6 --layout split --streamers workers/live_clipper/gta6_streamers.json`. You can start it early: offline channels wait (Streamlink retries) and are picked up when they go live.
   - 7+ channels at once: renders share `--render-slots` (default: CPU cores / 2) so the first clips finish fast instead of all of them crawling. Lacy's crew often share moments; `plan` collapses those into one FIRST-lane post.
7. **Review loop:** watch the `BEST CLIPS` leaderboard (`leaderboard.json`). Post high-scoring, spoiler-free drafts at once. Wait for the captioned final on the rest. Use `post.txt` for the title, hook and hashtags.
8. **After hour 1:** re-tune with `spikes` on the logged chat if a channel is over- or under-firing.

## Posting Rules

- Story clips are flagged `spoiler_risk`. **Never put plot points in titles or thumbnails** during launch week. The story title template is deliberately "reacts to GTA 6 (no spoilers)".
- Keep clips short and reaction-led (facecam + gameplay). Don't upload raw cutscenes, full missions or leaked material.
- Clip streamers who allow clipping. Many big streamers welcome it, and some run paid clip programs. Credit the streamer in the title (the templates do).
- Every clip is `PENDING_REVIEW`. You decide and you post ([[Export]] boundary).

Back to [[Home]].
