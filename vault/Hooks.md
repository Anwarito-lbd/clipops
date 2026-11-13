---
tags:
  - pipeline
---

# Hook Detection & Editorial Copy

Upstream: [[Scoring]], [[RetentionPacing]] · Downstream: [[Editing]], [[Remotion]]

Implemented in `workers/clip_ranking/hooks.py` (`classify_hook`), `workers/clip_ranking/rank.py` (`_score_text`), and `workers/caption_generation/generate.py` (`generate_account_copy`).

## Hook Regex Taxonomy

`classify_hook(text)` evaluates five ordered compiled patterns — the first matching pattern classifies the opening hook:

1. `question`: `\b(why|how|what|who|when|where|can we|did you)\b|\?`
2. `surprising_fact`: `\b(secret|nobody|surprising|actually|truth|fact)\b`
3. `controversy`: `\b(wrong|vs|versus|hate|controversial|debate|but)\b`
4. `drama`: `\b(wait|shocking|insane|crazy|hit different)\b`
5. `payoff`: `\b(so|therefore|result|finally|that'?s why)\b`
6. Fallback: `generic`

## Opening-Line Weighting

In `workers/clip_ranking/rank.py`, `_score_text` isolates the first sentence (`opening = t.strip().split(".")[0]`) and assigns `strong_opening = 90.0` when `HOOK_WORDS` matches inside the opening sentence (vs `60.0` otherwise, `20.0` if empty). [[RetentionPacing]] weights `hook_score` at `0.18` in the composite blend.

## Editorial Style Presets (No Duplicate Clones)

Top-ranked clips are assigned round-robin across three editorial style presets (`dramatic`, `educational`, `commentary`) via `generate_account_copy` so each exported package uses distinct pacing, hook framing, and caption copy rather than cloning one cut. See [[Models]] and [[OperatorUI]].
