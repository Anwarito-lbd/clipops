# Daily operator workflow

**Date:** 2026-08-02
**Status:** Approved
**Scope:** What the operator actually does each day, what the dashboard must show to support it, and which parts become automatic over time.

---

## Problem

The strategy spec settled *which* campaigns to clip and the pipeline now produces good clips. Neither addresses the thing that decides whether this earns anything over months: the human loop. Twelve posts a day means twelve manual TikTok uploads and twelve Content Rewards submissions, because those gates stay manual by design.

A workflow that requires constant attention gets abandoned. The design target is a routine that survives a bad week.

## Constraints

| Constraint | Source | Consequence |
|---|---|---|
| ≥3 hours between posts on the same account | TikTok cadence research | Cannot post 12 clips in one sitting |
| Submit to Content Rewards within ~1 hour of posting | Whop clipping guidance | Scheduled posts firing while away risk rejected submissions |
| Completion rate has no API | TikTok Creator Center only | The highest-signal metric cannot be captured automatically |
| Operator budget 60–90 min/day | Stated | Total of all touchpoints must fit |
| 4 accounts × 3 posts/day | Strategy spec | 12 posts/day, ~360/month |

The submission window is the binding one. Sources conflict on whether views count from post time or submission time, but agree a tight submission window exists and that missing it means not getting paid. **Verify the actual rule per campaign via the extension's Brief button** — if some campaigns allow longer windows, scheduled batches become viable for those specifically.

## Shape: three posting sittings, one production session

Posting splits into three sittings because the 3-hour gap is *per account*. One clip to each of the four accounts per sitting yields four-hour gaps for free:

```
~09:00  accounts 1,2,3,4
~13:00  accounts 1,2,3,4   (4h gap per account)
~17:00  accounts 1,2,3,4   (4h gap per account)
```

Three touchpoints instead of twelve, the operator is present when each post goes live so submission is immediate, and each sitting is 12–15 minutes from a phone.

Production — uploading footage, reviewing clips, approving — is separate and happens **once every two days** at a desk, covering 24 clips. Approved clips wait in the queue until their posting slot, so the posting sittings are purely mechanical: no reviewing, no deciding.

### Alternatives rejected

**Scheduling all 12 via TikTok web.** Appears to collapse everything into one session, but scheduled posts publish while the operator is away, and the link cannot be submitted before it exists. Against a ~1 hour submission window that risks the entire clip, not just some views. It also saves no touchpoints, since submission still requires coming back.

**Twelve individual posting moments.** Maximum control and trend responsiveness, but requires attention roughly hourly. This is the pattern most likely to be abandoned, and the research is consistent that cadence consistency outweighs per-post optimisation.

**One sitting, 4 posts/day.** Genuinely viable and the least demanding option, but the 3-hour gap caps it at one post per account. That is 120 posts/month, raising the bar from ~1,600 to ~4,750 views per clip for the same target — a bet on clips performing well rather than merely consistently, on accounts still warming up.

## Daily timeline

| When | What | Time |
|---|---|---|
| Desk session (every 2 days) | Upload/confirm footage. Review surviving clips best-first: watch, read the hook and rationale, approve or reject. | 20–30 min per session |
| Sitting A ~09:00 | Post 4 clips, paste each URL, submit to CR immediately | 12–15 min |
| Sitting B ~13:00 | Same, next 4 | 12–15 min |
| Sitting C ~17:00 | Same, final 4 | 12–15 min |
| Evening | Log yesterday's view counts | 2–5 min |

The 20–30 minute desk figure assumes auto-reject and auto-sort are in place, so 24 clips arrive pre-filtered and ordered. Without them, budget 45–60 minutes for the same batch.

Averaged across two days this lands at roughly **55–65 min/day**, inside budget. Only the desk session needs a desk.

**During week 1 the ramp applies.** The strategy spec starts at 8 posts/day, which is 2 posts per account — so week 1 runs **two sittings** (~09:00 and ~15:00, giving 6-hour gaps), moving to three from week 2.

## What the dashboard must show

Home currently shows a progress bar against the monthly target. The daily loop needs a different primary screen: **one view that says what to do next.**

- **Post-now card per sitting** — the 4 clips due, each with account, thumbnail, copy-ready caption, and an Open TikTok button
- **Countdown to the next sitting**, so being early or late is obvious
- **Submit-now nag** — any post marked posted but not yet submitted stays red until cleared. This is the item that directly costs money, so it gets the loudest treatment
- **Blocked items** — clips awaiting approval, assets where speech recognition failed, campaigns nearing their per-clipper cap
- **Queue depth** — how many approved clips remain, so the operator knows when the next desk session is due

## Progressive automation

The desk session shrinks as evidence accumulates. The gate between phases is data, not a calendar.

| Phase | Desk session (per 2 days) | Automated |
|---|---|---|
| Week 1–2 | 20–30 min | Auto-reject and auto-sort. The operator sees only survivors, best first |
| Week 3+, once correlation is established | ~10–15 min | Auto-approve above a proven score threshold; operator spot-checks ~20% |
| Later | ~5 min | Approval automatic; operator reviews flagged edge cases only |

**Automatic now, safely:**
- Footage ingest (auto-download plus watched folder)
- Auto-reject clips that fail compliance, fall below a score floor, or derive from a fabricated transcript
- Sort survivors by score so the best decisions come first

**Approval stays manual until proven, for three specific reasons:**

1. **Compliance does not inspect the video.** `run_compliance_check` receives `has_logo=None`, `has_cta=None`, `has_external_music=False` as hardcoded arguments (`apps/api/app/tasks.py`). It checks caption text and duration, never a pixel or a waveform. A passing compliance result is not evidence the clip complies.
2. **The ranker is unvalidated.** The LLM ranker outperformed regex on a seeded transcript, but no real clip has been posted. Auto-approving on a score nothing has verified against real performance is not justified yet.
3. **The blast radius is the accounts.** A rejected Whop submission costs one clip. A pattern of weak clips costs an account's algorithmic standing, and accounts are the scarce asset.

The promotion criterion is explicit: **C5 must show the predicted score correlates with observed views.** If it does not correlate, the ranker gets fixed rather than automated.

## Metrics capture

Completion rate is roughly twice-weighted in TikTok ranking and has no API. Twelve hand-entered numbers a day is a chore that stops happening within a fortnight.

**Views daily, completion weekly on a sample.** Views are one number per clip and are needed for earnings regardless. Completion rate is captured for around ten clips once a week — enough to compare hook variants and to test predicted-versus-actual correlation, without a daily tax.

## Missing a day

Recovery must not compound the problem.

- **Never double-post to catch up.** Stacking posts inside the 3-hour window is the actual risk, more than a missed slot.
- Missed clips roll into the next day's queue, oldest first.
- If the backlog exceeds one full day, the dashboard recommends **dropping** the excess rather than clearing it. A steady cadence outperforms raw count, and a catch-up dump spends per-campaign caps for less reach.

## Implementation implications

1. **Post-now view** — new primary dashboard screen driven by the posting schedule, replacing the progress bar as the default landing.
2. **Schedule model** — sitting times, per-account assignment, 3-hour spacing, and the two-week ramp.
3. **Submission tracking** — posted-but-not-submitted becomes a first-class alert state with elapsed time against the campaign's stated window.
4. **Auto-reject and sort** — a score floor plus compliance and transcript-engine filters applied before clips reach review.
5. **Queue depth signal** — approved-clip count and days of runway, driving when the next desk session is due.
6. **Completion-rate field** — optional per-clip input, with a weekly sampling prompt rather than daily.
7. **Auto-approve threshold** — configurable, defaulting to off, enabled only once correlation is demonstrated.

## Open items

- **The per-campaign submission window is unverified.** General guidance says ~1 hour; the actual rule per campaign comes from the Brief button. If longer windows exist, scheduled batches become viable for those campaigns and the sitting count could drop.
- **Sitting times are placeholders.** 09:00/13:00/17:00 satisfies the spacing rule but is not optimised for audience activity. Once per-clip view data exists by posting hour, these should be re-derived.
