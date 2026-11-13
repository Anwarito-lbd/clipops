---
tags:
  - pipeline
---

# Export and posting

[[Editing]] writes `video.mp4`, `caption.txt`, `cover.jpg`, and `render-meta.json` under `storage/exports/{campaign}/account-{slot}`. [[Config]] decides eager versus queued execution. The operator still posts.

Before and after the render, `run_compliance_check` records hashtags, mentions, disclosure, duration, aspect ratio, forbidden phrases, duplicate export hash, and logo or CTA when required. An unverified logo (`has_logo is None` while `requires_logo` is true) fails the check. The test `test_compliance_unverified_logo_fails_when_required` locks that.

Clip status only moves along `ALLOWED_TRANSITIONS` in `packages/shared_types/constants.py`: `REVIEW_REQUIRED` to `APPROVED`, `EXPORTED` to `MANUALLY_POSTED`, `PAYOUT_READY` to `PAID`. There is no transition that posts or submits by itself.

The review UI loads `GET /api/versions/{id}/approval-card`. `expected_earnings` on that card is `campaign.expected_profit` from the scoring formula, not cash received. In the local session that field was 25.362 while Home reported current earnings 0.

Manual gates, from the product copy and the approve handler:

1. Approve the campaign, then click Join on Content Rewards.
2. Approve the clip in Review.
3. Download the package, post on TikTok, paste the URL, mark posted.
4. Submit on Content Rewards, then confirm cash-out.

`GET /api/operator/readiness` on this machine, after the sample upload and before any of those human clicks, returned score 40 against target 99. The done items were the three seeded accounts, one discovered campaign, footage processed, and a draft render. CUDA, Remotion, rotated secrets, an approved export, a TikTok URL, a submission, and logged views were not done.

Back to [[Home]], or the raw outputs in [[EXAMPLES]].
