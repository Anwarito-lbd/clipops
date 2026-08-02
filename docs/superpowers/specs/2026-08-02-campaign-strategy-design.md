# Campaign allocation and view-maximisation strategy

**Date:** 2026-08-02
**Status:** Approved
**Scope:** How ClipOps selects campaigns, allocates them across TikTok accounts, generates clips, and maximises views — within Content Rewards rules and TikTok policy.

---

## Problem

ClipOps produces compliant clips but has no strategy for *which* campaigns to join or *how to spread them across accounts*. The operator asked directly: join one campaign per account, or join many and post one clip per campaign?

Two constraints make this non-trivial:

1. **Content Rewards caps payout per clipper per campaign.** A campaign's worth is bounded by that cap, not by its CPM. Scaling earnings therefore means running several campaigns concurrently, not finding one great campaign.
2. **TikTok rewards niche consistency.** Posting unrelated topics on one account prevents the algorithm from learning who to show it to, capping reach near the initial 200–500 test batch.

These pull in opposite directions: caps push toward *many* campaigns, the algorithm pushes toward *topical focus*. The design resolves this by grouping campaigns into per-account topic lanes.

## Operating parameters

| Parameter | Value |
|---|---|
| TikTok accounts | 4 (aged but dormant) |
| Posts per account per day | 3 (after warm-up) |
| Total daily posts | 12 (~360/month) |
| Operator time budget | 60–90 min/day |
| Monthly target | £1,000 floor, not a ceiling |
| Platform fee | 7% (multiplier 0.93) |

## Research findings

Sourced 2026-08-02. These drive the design decisions below.

**Distribution and ranking**
- Videos are released to an initial test batch of 200–500 users; strong engagement promotes them to successively larger waves.
- **Completion rate weighs roughly 2× any other engagement metric. The viral threshold is now 70%+, up from 50% in 2024.**
- Rewatch rate above 15–20% is a strong signal. Shares are the strongest engagement signal.
- Niche-specific content is prioritised; jumping topics confuses the algorithm and dilutes reach.
- Authentic human-feeling content is favoured over obviously AI-generated output.

**Hooks**
- 71% of users decide within 3 seconds, but the **median scroll-stop is 1.5–2 seconds**.
- **A verbal hook combined with a visual pattern interrupt produced 47% higher 3-second retention than words alone.**
- Effective techniques: start mid-action rather than on a static frame, bold animated text, a quick zoom within the first second.
- Testing 3–5 hook variants and comparing completion rates is the recommended optimisation loop.

**Cadence**
- 1–3 posts/day/account is optimal; for clipping accounts specifically, 1–2/day across 5–6 days/week.
- **Minimum 3 hours between posts on the same account.**
- Consistency beats perfection — the algorithm builds a distribution baseline around the posting pattern.
- First meaningful growth spike at 2–4 weeks; compounding growth at 3–6 months.

**Content Rewards specifics**
- Rates run $0.20–$6 per 1,000 views, **averaging around $1**. Earnings accrue only while campaign budget remains.
- **Per-post transformation is required**: unique captions, different trims, different opening frames, varied crops. TikTok flags low-originality reposts, risking bans that forfeit unverified views. Whop also rejects duplicate-looking submissions across clippers.
- **Views count only from when the post is trackable** — submit to the campaign immediately after posting.

## Decision: niche lanes

Each account owns one **topic**. Within that topic it runs 2–3 concurrent campaigns and draws all its daily posts from that pool. When a campaign exhausts, it is replaced by another campaign *in the same topic*, so the account's subject never shifts.

### Alternatives rejected

**One campaign per account, swapped when capped.** Simplest and maximally consistent, but when a campaign caps out a same-topic replacement must be ready that day or the account goes dark. One campaign's footage rarely sustains 3 quality clips/day indefinitely. Concentration risk if a brand pauses the campaign.

**Max-CPM chase — join everything, always post the best-paying clip.** Rejected. It fights the algorithm: accounts never establish a topic, so reach stays pinned near the test batch. A $10 CPM on 400 views pays $3.72; a $1 CPM on 20,000 views pays $18.60. High CPM on low reach is worthless, and this is the pattern the research explicitly identifies as failing.

### Lane assignments

| # | Identity | Campaign pool | CPM | Rationale |
|---|---|---|---|---|
| 1 | **Business & Money** | Paul Cheek, Fynn Röber, Business Basics | $2–$5 | Deepest supply, highest sustained rates, talking-head suits a speech-keyword ranker, high share velocity |
| 2 | **AI & Tech** | Sozee, Inspoy, Smartlead | $3 | Consistent across the whole cluster with no outlier dependency |
| 3 | **Podcast Moments** | Call It a Day, Brandon Mason, Sozee Podcast | $1–$3 | Best clips-per-hour — one long download yields 10+ clips; volume offsets the lower rate |
| 4 | **Flex / Entertainment** | Summer Beats, GORDO, plus exceptional campaigns | $0.80–$10 | Captures outliers and runs hook A/B tests before findings roll out to lanes 1–3 |

Music is the flex lane rather than a core lane: the $10 Summer Beats campaign was a single outlier already 40% drained, while the rest of music (GORDO $0.80 ×2, REN.Y.C $1) sits at roughly the platform average. Music clips also contain little speech, which starves the transcript-driven ranker.

**Exclusions.** Gambling campaigns (ROOBET, Fliff, BizBet, Modo.US) are excluded despite large budgets — TikTok restricts gambling content and the account risk outweighs the rate.

### Invariants

1. **No campaign appears in more than one lane.** This is what prevents four accounts producing similar clips from the same source — the pattern that triggers low-originality flagging.
2. **Replacements are always same-lane**, so an account's topic never changes.
3. **Join a replacement at 75% of budget consumed or 75% of the per-clipper cap** — before the pool dries up.
4. Existing auto-reject at 90% budget utilisation stays.

## Clip generation

Campaign requirements are a hard gate. Optimisation happens strictly inside them.

- **Default 15–25s.** Use 25–40s only where a brief mandates a longer minimum. The 40–60s band is dropped — a 48-second clip cannot realistically clear a 70% completion bar.
- **Hook lands by 1.5s**, combining a verbal hook with a visual pattern interrupt (zoom or motion within the first second). Text overlay alone is measurably weaker.
- **Start mid-action**, never on a static frame.
- **Per-account transformation is functional, not cosmetic**: distinct trim points, opening frame, crop, and caption per account.
- **3–5 hook variants per campaign**, ranked on observed completion rate once ~50 clips of data exist (the existing cohort learning service already does this; it needs completion rate as an input, not just views).

## Daily rhythm

Twelve posts across four accounts, respecting the 3-hour same-account minimum:

```
09:00 acct1   10:00 acct2   11:00 acct3   12:00 acct4
13:00 acct1   14:00 acct2   15:00 acct3   16:00 acct4
17:00 acct1   18:00 acct2   19:00 acct3   20:00 acct4
```

Submit each post to Content Rewards **immediately** — batching submissions discards views accrued before the link became trackable.

**Warm-up ramp.** The accounts are aged but dormant; jumping straight to 3/day is anomalous. Week 1: 1/day/account. Week 2: 2/day. Week 3 onward: 3/day. Expect 2–4 weeks before the algorithm re-learns each account.

**Known tension.** The research recommends 1–3/day generally but 1–2/day across 5–6 days/week *for clipping accounts specifically*. Running 3/day/account, 7 days a week, sits at or above that upper bound. This is a deliberate choice: total volume is what makes the target reachable, and the risk is mitigated by strict per-account topical consistency and the warm-up ramp. **If per-clip reach degrades as volume rises, the lever is to drop to 2/day/account (8/day total) rather than to add a fifth account** — the research is consistent that cadence quality beats raw count. Track views-per-clip weekly against the ramp to detect this.

## Earnings model

Blended CPM across the four lanes ≈ **$2.40**, giving **$2.23 net per 1,000 views** after the 7% fee.

Figures assume **£1 ≈ $1.27**; Content Rewards pays in USD while the target is set in GBP, so the FX rate is a real input. Verify it before treating these as commitments, and re-derive if it moves materially.

| Target | Views/month | Views/post (360 posts) | At 70% approval |
|---|---|---|---|
| £1,000 | ~570,000 | ~1,600 | ~2,300 |
| £2,000 | ~1,140,000 | ~3,200 | ~4,500 |

These are ordinary clips rather than hits, which is what makes the target reachable at four accounts where it was not at two.

The blended $2.40 assumes lanes hold their observed rates. It is sensitive to lane 3 (Podcast Moments, $1–$3) and to how much of the flex lane's volume lands on low-rate music campaigns rather than outliers. At a pessimistic blended $1.50, £1,000 needs ~2,600 views/post before approval — still attainable, but the margin narrows.

## Implementation implications

Beyond the pipeline defects already scheduled:

1. **Account niche field** — `SocialAccount` carries a topic identity distinct from its edit style.
2. **Lane assignment** — campaigns map to exactly one lane; enforce the no-overlap invariant at assignment time.
3. **Cap early-warning** — surface campaigns crossing 75% of budget or per-clipper cap, with same-lane replacement suggestions.
4. **Duration bands** — drop 40–60s; default 15–25s; honour per-campaign minimums.
5. **Pattern interrupt** — ensure a zoom/motion beat lands inside the first second of every render.
6. **Transformation depth** — guarantee distinct trim, opening frame, crop and caption per account.
7. **Posting scheduler** — 3-hour same-account spacing, warm-up ramp, and a submit-now prompt on each post.
8. **Completion-rate capture** — the learning loop currently ingests views only; completion rate is the higher-signal metric and must be recorded.

## Open items

- **Per-clipper cap values are unknown.** No scanned brief stated one; the extraction patterns exist but need the campaign detail page, reached via the extension's Brief button. Until populated, the campaign ceiling falls back to remaining budget.
- **Lane assignments assume the previously scanned campaigns are still live.** The discovery table was reset on 2026-08-02; a fresh scan through the corrected parser must confirm supply per lane before any campaign is joined.

## Sources

- [TikTok Algorithm 2026: Watch Time, Completion Rate & How to Go Viral](https://www.go-viral.app/blog/tiktok-algorithm-2026/)
- [TikTok Algorithm 2026: The 7 Signals That Decide If You Go Viral — Socialync](https://www.socialync.io/blog/tiktok-algorithm-2026-what-works-now)
- [TikTok Algorithm 2026: How Organic Distribution Really Works — TokPortal](https://www.tokportal.com/learn/tiktok-algorithm-2026)
- [How TikTok's Algorithm Works in 2026 and 15 Tactics to Go Viral — Darkroom](https://www.darkroomagency.com/observatory/how-tiktok%E2%80%99s-algorithm-works-in-2026-and-15-tactics-to-go-viral)
- [How Often to Post on TikTok in 2026 — JoinBrands](https://joinbrands.com/blog/how-often-to-post-on-tiktok/)
- [TikTok Posting Schedule 2026 — Hummingbird](https://www.hummingbird.agency/insider-tips-mastering-tiktok-consistency-for-success/)
- [How many clips to post per day in 2026 — Cut.Pro](https://cut.pro/en/blog/how-many-clips-to-post-per-day-2026)
- [TikTok Ad Hooks: Win the First 3 Seconds in 2026 — AdRoast](https://www.adroast.ai/blog/tiktok-ad-hooks-first-3-seconds)
- [TikTok Algorithm 2026: 7 Hooks for Retention — HypeNest](https://hypenest.ai/blogs/tiktok-algorithm-2026-video-hooks-retention)
- [The 3-Second Hook: Why TikTok Videos Win or Die in 2026 — Hansen Insights](https://hansencommerce.com/insights-tiktok-hook-3-seconds)
- [Whop Clipping: How Content Rewards Work (2026) — WhopReviews](https://www.whopreviews.com/guides/whop-clipping)
- [Content Rewards Explained — Highstyle](https://www.highstyle.ai/insights/content-rewards-explained)
- [Whop Clipping Guide: Content Rewards 2026 — OpenClip](https://openclip.app/guides/whop-clipping-guide)
