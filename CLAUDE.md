# CLAUDE.md — ClipOps

Standing instructions for this repo. General engineering conventions live in
`../CLAUDE.md` (think before coding, simplicity, surgical changes, goal-driven
execution) — this file covers only what is specific to ClipOps.

See `README.md` for what the system does and `docs/USER_WORKFLOW.md` for the
daily loop. Do not duplicate those here.

## What this is

A single-operator clipping business on Content Rewards (Whop). Not a product for
others: no billing, no multi-tenancy, and none is wanted. Money flows inward
only. Long-form footage in, ranked 9:16 clips out, posted and submitted by hand.

## The failure mode this codebase keeps having

**Stages report success while producing unusable work.** Every serious incident
so far is this shape, not a crash:

- Ranking fell back to keyword matching whenever it ran outside the API server,
  because `llm_rank` reads `os.environ` while pydantic-settings loads `.env`
  into a settings object. Two full batches shipped keyword-ranked.
- Scene detection had no timeout, so the fallback beneath it was unreachable —
  one source ran 9h14m and blocked everything queued behind it.
- The renderer emitted 96kHz AAC (loudnorm runs at 192kHz internally), which
  most players decode as silence. Every check passed. The clips had no voice.
- A hard-coded duration lookup keyed on an operator-editable column raised
  KeyError and failed an entire three-source run.

So, when touching this pipeline:

- **A fallback that cannot be reached is not a fallback.** Anything that can run
  unboundedly needs a budget, or the degraded path is dead code.
- **Degrading silently is worse than failing.** If ranking cannot reach an LLM,
  that must be loud. The keyword ranker once scored *"Weather's been alright"*
  as the best clip in a transcript, and picked football chatter out of a video
  about losing everything.
- **Verify the artifact, not the exit code.** Check duration, sample rate,
  audio level and the ranker actually used — not that ffmpeg returned 0.

## Hard external constraints

Not negotiable in code, and not ours to relax:

- **≥3 hours between posts on the same TikTok account.** This is why posting is
  organised into sittings rather than one batch.
- **Submit the link within ~1 hour of posting.** A late submission can be
  refused outright — the one backlog that loses money rather than delaying it.
- **Joining, posting, submitting and cashing out stay manual.** A campaign brief
  warned *"BOTTING WILL NOT BE TOLERATED, INSTANT BAN"*. Never automate these.
- Completion rate is roughly double-weighted and the viral bar is ~70%, which is
  why clips target 15–25s even when a campaign permits 60.
- Approval rates are published per campaign and can be as low as 3%. Never
  assume 70% — it once overstated a campaign's value by 26×.

## Safety is a selection constraint, not a filter

Asked to maximise virality, the ranker chose *"Is that a Nazi flag?"* as its top
clip, reasoning that controversy drives shares. It was not malfunctioning; the
prompt asked for exactly that.

- Enforce safety **in code**, not only in the prompt. A prompt is a request.
- Check the hook, the title, **and the speech inside the clip's window**.
- The cost is asymmetric: a rejected clip costs one clip, a banned account costs
  every future clip plus unverified views already accrued.
- Watch slang — *"We're putting $4,800 on Portugal"* contains no betting keyword.
- Do not over-block: *"I spent $100,000 on a random Thursday"* is a real video
  title and must pass.

## What compliance does not check

`compliance_checker` covers caption text, duration, aspect ratio and
duplication. It **cannot see** logos, on-screen CTAs, or background music. A
passing compliance report is not evidence a clip complies — the operator must
watch it. Say this plainly rather than implying clips are cleared.

## Pick footage by measured speech density

Never by title. A 13-minute video with a promising title had **no
auto-subtitles at all** and yielded 4–14s of usable speech; a lesson-shaped
title measured 69 WPM. Pull auto-subtitles first (cheap, no download) and
compare words-per-minute — the source that produced the benchmark batch sits at
175 WPM.

## LLM backends

- **NVIDIA is primary, Gemini is fallback and currently out of quota** (429,
  monthly spending cap). The operator declined to pay, so do not assume Gemini.
- **Pin the model explicitly.** NVIDIA retires hosted models on a schedule and a
  retired one returns 410 — `deepseek-v4-flash` died mid-run and silently
  dropped a batch to keyword ranking.
- Distinguish **529 (overloaded, retry)** from **429 (quota spent, never
  clears)**. Treating them alike once cost a whole run.
- Prefer non-reasoning models for ranking: `nemotron-nano-9b-v2` ran 100s vs
  898s for a 49B reasoning model **and** recovered a benchmark clip it missed.

## Commands

```bash
pytest tests -q                                    # 38 tests, ~30s, no GPU needed
```

```bash
cd apps/api && PYTHONPATH=../.. uvicorn app.main:app --reload
```

```bash
cd apps/dashboard && npm run dev
```

Tests run without torch/whisperx — those are a separate CUDA install
(`scripts/install_whisperx_cuda.py`). CI installs only
`apps/api/requirements.txt`.

## Layout

| Path | Holds |
| --- | --- |
| `apps/api` | FastAPI app, SQLAlchemy models, Celery tasks |
| `apps/dashboard` | Next.js operator dashboard |
| `packages/` | Campaign parsing/scoring, compliance, posting queue, services |
| `workers/` | Transcription, scene detection, ranking, rendering, captions |
| `vendor/` | Third-party checkouts and model weights — see `vendor/README.md` |
| `docs/superpowers/specs/` | Design specs, dated |
| `storage/` | Sources, work dirs, delivery folders (gitignored) |

## Conventions

- Comments explain **why**, especially where a line encodes a past incident.
  Several exist only because something failed; do not strip them as noise.
- `storage/ready_to_post/` is disposable and rebuilt from renders — never the
  source of truth.
- Never commit `.env`, `*.db`, media, or `vendor/` payloads.
- The operator pastes API keys into chat. Remind them to move keys to `.env` and
  rotate anything pasted.
