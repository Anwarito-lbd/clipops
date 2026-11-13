---
tags:
  - pipeline
---

# Scoring

[[Transcription]] supplies text and scene windows. [[Hooks]] classifies the winning lines. Both campaign score and clip score are deterministic functions in the repo, not a hosted model.

## Campaign score

Weights sum to 100. A hard reject (budget at least 90% used, fake engagement, no rights, geography miss, and the other flags in `score_campaign`) forces `is_recommended` false.

```6:14:packages/shared_types/constants.py
SCORE_WEIGHTS = {
    "remaining_budget": 20,
    "cpm": 15,
    "audience_match": 20,
    "footage_quality": 15,
    "requirement_simplicity": 10,
    "viral_potential": 15,
    "competition": 5,
}
```

`CampaignScoringService` then labels the result: `HIGH_PRIORITY` when the score is at least 85 and profit per hour is at least 25, `CONSIDER` when the score is at least 70, otherwise `AVOID`. A campaign can be eligible and still land on `AVOID` because the score is under 70. The offline VoltPop brief scored 65.0 with recommendation `AVOID` and an empty reject list. See [[EXAMPLES]].

## Clip score

`rank_segments` scores overlapping transcript text with hook, conflict, emotion, and payoff regexes. `ClipRankingService` folds those into one 0–100 score and keeps the top slice for render.

```78:95:packages/services/clip_ranking.py
            total = (
                hook_score * 0.18
                + curiosity * 0.12
                + conflict * 0.12
                + emotion * 0.12
                + payoff * 0.18
                + clarity * 0.12
                + fit * 0.10
                + duration_score * 0.06
            ) - dead_air * 0.05
            total = round(max(0.0, min(100.0, total)), 2)

            if total >= 80:
                pred = "HIGH"
            elif total >= 60:
                pred = "MEDIUM"
            else:
                pred = "LOW"
```

`process_asset` asks for `keep=20` and `select=5`. The service returns `selected = reports[: max(3, min(select, len(reports)))]`, so a short video with three scenes selects three. Predicted performance on the silent demo was `MEDIUM` because those totals sat between 60 and 80.

Next: [[Hooks]].
