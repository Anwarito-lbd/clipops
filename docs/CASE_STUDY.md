# Case study: keeping the last click human

I built ClipOps for a single operator who already has a Content Rewards login and a few TikTok accounts. The job is to turn a brief and a long source into a handful of different vertical cuts, with the disclosure and hashtags in the caption, and to stop before anything that spends the account: Join, Post, Submit, cash-out.

## What I refused to automate

Those four actions are not missing features. `ALLOWED_TRANSITIONS` has no edge that posts. The extension’s manifest says it never auto-posts or auto-submits. Approving a discovered campaign returns next steps whose second line is “Click Join yourself — ClipOps does not auto-join.” `GET /health` reports `automation_boundary: human_approval_manual_posting`. The sidebar label “~85–90% automated” is copy in `apps/dashboard/components/sidebar.tsx`. I have not measured that percentage.

## How a clip gets chosen

I did not put an LLM in the ranker. A campaign score is a weighted sum of budget remaining, CPM, audience, footage, simplicity, viral potential, and competition (`SCORE_WEIGHTS`, which sum to 100). Hard rejects are explicit: budget utilisation at or above 0.90, fake engagement, missing rights, a geography miss. Soft labels are separate. Under 70 the recommendation is `AVOID` even when nothing was rejected. That showed up on the VoltPop sample: score 65.0, recommendation `AVOID`, empty `reject_reasons`.

Inside a video, scenes come from PySceneDetect when it imports, otherwise from 8 second windows. Text overlapping each window is scored with small regexes for a hook, conflict, emotion, and payoff. The blend in `ClipRankingService` weights hook and payoff at 0.18 each. At least 80 is `HIGH`, at least 60 is `MEDIUM`, otherwise `LOW`. I keep up to 20 candidates and render a handful, then assign them round-robin across accounts so three styles are not three exports of the same cut.

## What fails closed

Compliance treats “I could not see the logo” as a failure when the brief requires one (`has_logo is None`). Duration is checked against the brief, not against the duration band name. A 4 second scene rendered cleanly and then failed `4.0s not in [20, 45]`. I would rather hold a clip in `REVIEW_REQUIRED` than export a package the brief does not allow.

Speech is the other place I expected the machine to be missing. The order is WhisperX, then faster-whisper, then five canned sentences spread across the real duration. On this Linux box WhisperX was not installed. faster-whisper 1.2 crashed on PyAV 19 because `av.open` no longer takes `metadata_errors`. I feed it 16 kHz PCM from ffmpeg instead, so a missing keyword is not a dead pipeline. A pure tone still has no words. The engine returns empty segments, the heuristic fills in, and the asset records that string. Ranking still runs. The operator can see `transcript_engine=heuristic` on the asset.

The commentary style had a similar sharp edge. `drawbox`’s `w` and `h` are the box, not the frame. FFmpeg exited 234 and left a 0-byte file. `iw` and `ih` fixed it. The same upload, reprocessed, produced an 86,633-byte commentary MP4 next to the dramatic and educational files that had already rendered.

## What I actually ran

`pytest tests`: 17 passed in 12.25 seconds. The offline script produced the 12 second source, three PySceneDetect windows, the 65.0 campaign score, and a 4 second 1080×1920 dramatic cut of 86,902 bytes. The API, with eager Celery and no Remotion, reported stack readiness 67 and go-live score 40 out of a target of 99. Home showed £0 earned. The 8210 views and £2 planning CPM on that screen are the defaults in `ForecastService` when the performance table is empty. I did not post, submit, or cash out, so those checklist items stayed open on purpose.
