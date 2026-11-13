---
tags:
  - pipeline
---

# Scoring & Candidate Selection

Upstream: [[Transcription]], [[SceneDetection]] · Downstream: [[Hooks]], [[RetentionPacing]] · Configuration: [[Config]]

Implemented in `packages/services/campaign_scoring.py` (`CampaignScoringService`) and `packages/services/clip_ranking.py` (`ClipRankingService`).

## Campaign Brief Scoring

`SCORE_WEIGHTS` in `packages/shared_types/constants.py` sums to 100 (`remaining_budget` 20, `audience_match` 20, `cpm` 15, `footage_quality` 15, `viral_potential` 15, `requirement_simplicity` 10, `competition` 5). Explicit hard rejects (budget utilisation $\ge 0.90$, fake engagement, missing rights, geography mismatch) force `is_recommended = False`. Eligible briefs under score `70` still label `AVOID` (e.g. the `65.0` VoltPop sample in [[EXAMPLES]]).

## Clip Candidate Selection

1. `rank_segments` (`workers/clip_ranking/rank.py`) aligns overlapping transcript segments onto scene windows from [[SceneDetection]], ignoring windows `< 3s` and capping at `60s`.
2. `ClipRankingService.rank_footage` enriches each window with [[RetentionPacing]] telemetry and [[Hooks]] classification, keeps the top `keep=20` candidates, and selects `select=5` (`max(3, min(select, len(reports)))`) for editorial rendering.

Next: [[Hooks]] and [[RetentionPacing]].
