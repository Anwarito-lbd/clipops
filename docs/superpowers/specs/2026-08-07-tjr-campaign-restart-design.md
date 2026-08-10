# TJR campaign restart — sourcing, lanes and a reset-anchored schedule

Date: 2026-08-07
Status: implemented

The TJR campaign reopened. It runs daily, ~$3,300 at $1.00/1k views, resets
around 11:30 EST and **closes once the budget fills**, against 198 participants.
Five clips scoring 93–97 already existed from the August 5th run. This records
what changed to restart against the new campaign, and why.

## Volume: 9 posts/day, not 12

Four posts per account at TikTok's three-hour same-account minimum spans nine
hours. Anchored to the 11:30 EST reset that puts the fourth sitting at 01:30 in
the operator's local time — and, more importantly, roughly nine hours after a
budget that may already be full.

**Decision: three sittings of three, 15:30 / 18:30 / 21:30 UTC.** Nine posts,
all inside the window where the budget is plausibly still open. The fourth
sitting becomes the next day's first, at the next reset.

Rejected: keeping twelve and accepting 01:30 (back-loads three clips into a
likely-closed budget, and costs a nightly 1:30am phone session); starting before
the reset (those clips compete for the previous day's remainder); seeding the
fourth dormant account (adds a new account to the mix mid-campaign for three
extra posts).

## Source selection: measure speech density, never infer from titles

The ranker scores speech. A vlog with long silent b-roll yields nothing, which
is how a 13-minute video previously produced 4–14s of football chatter while a
37-minute trading-psychology video produced the 93–97 batch.

**Method: fetch auto-subtitles only — no video — and compute words per minute.**
One subtitle request per candidate instead of a 300MB download, and it is a
direct measurement rather than a guess from the title.

Measured against the channel, with the known-good source as a control:

| WPM | Length | Video |
|---|---|---|
| 238 | 16m31 | Why Everything Changes After Your First Payout |
| 201 | 13m21 | Your focus is your reality (reserve) |
| 188 | 69m41 | I Took A Trader From Broke To Rich In 30 Days |
| 187 | 8m57 | you owe it to yourself (reserve) |
| 186 | 35m25 | Beginners Guide To Pass A Prop Firm In 2026 |
| **175** | 37m16 | **9 Years of Trading Psychology — CONTROL, produced 93–97** |
| 147 | 18m14 | I spent $100,000 on a random Thursday |
| **69** | 59m04 | **Learn From My $80K Mistake** |
| **none** | 13m08 | **I LOST EVERYTHING — the vlog that failed** |

Two results justify the method on their own. `I LOST EVERYTHING` has **no
auto-subtitles at all** — YouTube found too little speech to caption it, which
is exactly the failure already observed. And `Learn From My $80K Mistake` scores
69 WPM behind a perfectly lesson-shaped title; selecting by title would have
walked straight into a second vlog.

The three picks above the control were downloaded, one per account lane.

## Account lanes

The three TikTok rows carried styles (`dramatic` / `educational` / `commentary`)
but generic notes, and `preferred_clip_length` / `preferred_hooks` were NULL —
the rows predate those columns, so `_sqlite_add_missing_columns` added them
empty and the seed values never applied. Both the seed and the live rows now
carry concrete trading sub-lanes.

`preferred_clip_length` for the educational lane moved from `25-40` to `18-28`.
Completion rate carries roughly double weight and the 2026 viral threshold is
70%, which a 40-second clip rarely clears.

**This breaks the "no campaign appears in two lanes" invariant deliberately.**
That rule exists to stop several accounts producing similar clips. Running TJR
across all three concentrates a new clipper on a live pool, and the accounts are
dormant with no established niche to protect. The lanes are therefore
**provisional** — they should be re-separated as soon as a second campaign is
joined.

Note: `preferred_hooks` and `audience_notes` are not currently read by the
ranker or renderer. Only `style` is. Lane differentiation today comes from which
source video feeds which account, not from these fields.

## Schedule: anchored to the reset

`packages/services/schedule.py` hardcoded `FULL_SITTING_HOURS = (9, 13, 17)` and
`RAMP_SITTING_HOURS = (9, 15)` as UTC integers, and returned only two sittings
while `days_active < 7`.

Changes:

- `build_schedule` accepts `anchor` ("HH:MM" UTC) and `sitting_count`. Sittings
  are computed from the anchor at `MIN_GAP_HOURS` intervals.
- Sitting times are **datetimes, not hour integers**. A day anchored late enough
  runs its last sitting past midnight, and comparing `now.hour` against a sitting
  hour silently reorders the day when that happens. Covered by a test.
- An explicit anchor overrides the ramp-week reduction. The ramp exists for
  measurement, but under-posting a budget that closes when filled forfeits the
  pool rather than buying data.
- Anchor and count live on `operator_settings` (`sitting_anchor_utc`,
  `sitting_count`), set to `15:30` / `3`.

Default behaviour with no anchor is unchanged.

## Parser: "LINK IN BIO" was being read as India

`_GEO` matched the bare word `IN`, so every brief containing "LINK IN BIO" — TJR's
included — parsed as `required_geo: ["IN"]`. That feeds `check_eligibility` and
`score_campaign`, both of which add a hard reject reason when required geo does
not intersect the operator's `["US", "CA"]` audience.

The campaign the operator is trying to run could therefore score itself
ineligible the moment its brief was captured. `IN` is now matched as `India`
instead, normalised back to `IN`.

Verified against the stored TJR brief (`[]` after, `["IN"]` before) and against
a genuine "creators in India only" brief (still `["IN"]`).

## Known gaps, unchanged

- No face-tracked cropping — `vendor/claude-shorts/compute_reframe.py` needs
  mediapipe, which is not installed.
- Compliance checks aspect ratio, duration and audio. It **cannot** see logos,
  on-screen CTAs or music. A passing compliance report is not evidence that a
  clip complies; every clip still needs eyes before posting.
- Gemini remains out of quota. NVIDIA / DeepSeek is the ranker backend.
