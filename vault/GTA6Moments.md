---
tags:
  - playbook
  - gta6
---

# GTA 6 Moment Taxonomy

Playbook: [[GTA6]] · Detector & ranking: [[LiveClipping]] · Hook copy: [[Hooks]] · General scoring: [[Scoring]]

Each moment category has a chat/transcript signature, a virality prior (the ranking's `moment` component, 10/100 points) and a post title template. Chat hits are counted per 10 s bucket. Words the streamer actually says count double.

| Category | Chat / speech signature | Prior | Title template |
| --- | --- | --- | --- |
| `chase` | wanted, N stars, cops, police, SWAT, helicopter, getaway | 1.00 | `{streamer}'s first police chase in GTA 6 went crazy` |
| `glitch` | glitch, bug, physics, ragdoll, T-pose, flying car, launched | 1.00 | `GTA 6 physics broke {streamer}` |
| `fail` | wasted, busted, died, o7, crashed, missed | 0.90 | `{streamer} did NOT expect this in GTA 6` |
| `funny` | LMAO, KEKW, OMEGALUL, ICANT, NPC, Florida man, gator | 0.90 | `{streamer} vs GTA 6 NPCs` |
| `heist` | heist, robbery, bank, store, loot, cash | 0.85 | `{streamer}'s first GTA 6 robbery` |
| `graphics` | graphics, realistic, looks real, ray tracing, water | 0.70 | `{streamer} can't believe GTA 6 graphics` |
| `world` | Vice City, Leonida, map, beach, easter egg, hidden | 0.70 | `{streamer} explores Vice City in GTA 6` |
| `story` | Lucia, Jason, cutscene, twist, ending, mission | 0.50 ⚠ spoiler | `{streamer} reacts to GTA 6 (no spoilers)` |

## Why These Priors

- **Chases, glitches, fails** are self-contained: they make sense with no context, loop well, and have a clear payoff. That's the same standalone-clarity idea [[RetentionPacing]] rewards in podcasts.
- **Graphics / world** reactions spike hardest in the **first hour** (first impressions) and then fade, so post those fast.
- **Story** moments draw huge chat spikes but carry spoiler and takedown risk, so they're down-weighted and flagged rather than dropped.

## Hook Line

The clip's on-screen hook comes from, in order: the line the streamer says at the loudness peak (from Whisper), then chat's most-spammed full message ("SWAT INCOMING"), then the top chat words.

## Extra Hype Vocabulary

The profile adds GTA chat words to the detector's hype counter (`wasted`, `busted`, `5 stars`, `vice city`, `leonida`, `lucia`, `jason`, `ragdoll`, `clip that`, `run it back`, …). Add your own per run with `--hype WORD` (repeatable).

Back to [[Home]].
