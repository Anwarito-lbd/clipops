---
tags:
  - pipeline
  - live
---

# Live Clipping (Chat-Spike Clipper)

Upstream: [[Ingest]] · Uses: [[Transcription]], [[Editing]], [[Hooks]] · Ranked like [[Scoring]] · Game knowledge: [[GTA6]], [[GTA6Moments]] · Ends at: [[Export]]

Implemented in `workers/live_clipper/`. Goal: **be first to the best clips** — clip the stream *while it is still live*, rank every moment, and hand you a post-ready kit. Posting stays manual.

## Pipeline

| Stage | Module | What it does |
| --- | --- | --- |
| Record | `recorder.py` (`SegmentRecorder`) | `streamlink --stdout … \| ffmpeg -c copy -f segment` into **2 s** MPEG-TS segments + `segments.csv`. Ring buffer (`--retain`, default 30 min). |
| Chat | `chat.py` (`TwitchChatReader`) | Anonymous read-only IRC (`justinfanNNNNN`), `tmi-sent-ts` server timestamps, auto-reconnect. Logs `chat.jsonl` for replay/tuning. |
| Detect | `spikes.py` (`ChatSpikeDetector`) | 10 s buckets vs rolling 3 min baseline. Fires **mid-bucket** the instant thresholds clear. |
| Cut | `cutter.py` | Draft: one ultrafast pass straight from segments. Final: frame-accurate cut → Whisper → captions → 9:16. |
| Rank | `ranking.py` | 0–100 score, re-scored live while chat keeps reacting. `leaderboard.json`. |
| Profile | `profiles.py` | Game vocabulary, moment categories, thresholds, titles — see [[GTA6Moments]]. |

## Spike Math

A bucket is a spike only if **all** hold (per-user cap of 2 msgs/bucket kills spam bots):

- `count ≥ min_messages`
- `count / median(baseline) ≥ ratio_threshold` (default 2.5; GTA 6 profile 2.0)
- robust z = `(count − median) / max(1.4826·MAD, √median)` ≥ `z_threshold`
- Poisson tail `P(X ≥ count | λ = median) ≤ 1e-4` — added after a test showed λ=5 chats firing on noise (~4 false clips/hour)
- outside the cooldown of the previous spike (default 45 s, GTA 40 s)

## Latency Budget ("be first")

Clip window ends `tail_seconds` (6 s) **after detection**, so the minimum wait is the tail itself. Measured on a 4-core CPU sim: draft **14.9 s** after spike (≈8 s tail capture + 7.4 s render), captioned final ≈40 s. GPU (`--device cuda --model small`) and a faster CPU cut both.

Post the **draft** when a top-ranked moment is spoiler-free and speed matters; otherwise wait ~30 s for the captioned `clip.mp4`.

## Ranking Weights

`chat_velocity 22 · sustain 18 · audio 14 · volume 10 · hype 10 · moment 10 · chat_intensity 8 · speech 8`. Sustain (how long chat stays elevated) is only final once chat calms down, so live scores rise as the reaction continues. Unlike the podcast text scorer in [[Scoring]] / [[RetentionPacing]], stream clips are judged mostly on audience reaction.

## Commands

```bash
python -m workers.live_clipper live kaicenat caseoh_ --profile gta6 --streamers streamers.json
python -m workers.live_clipper spikes storage/live/<session>/<channel>/chat.jsonl --profile gta6
python -m workers.live_clipper replay vod.mp4 chat.jsonl --profile gta6 --streamer kaicenat
```

Back to [[Home]].
