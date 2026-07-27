# ClipOps Full Audit

**Date:** 2026-07-27  
**Repo:** https://github.com/Anwarito-lbd/clipops  
**Scope:** Entire tree (~100 source files outside `.venv` / `node_modules`)

---

## 1. Current architecture

```text
Browser extension (logged-in Content Rewards tab)
        │ discover / brief / payout-watch
        ▼
Next.js dashboard (apps/dashboard)
        │
        ▼
FastAPI (apps/api) ── JWT ── SQLAlchemy
        │                      SQLite default | Postgres optional
        │ Celery (or inline sync)
        ▼
workers/  WhisperX*|scenes*|rank|captions|FFmpeg
packages/ parser|scoring|ranker|compliance|posting|analytics
templates/ Remotion compositions (render service = stub)
workflows/n8n/ notify stub (unwired)
```

\*Real engines optional; heuristic fallbacks ship by default.

**Safety boundary (intentional):** no auto Join, TikTok Post, CR Submit, or cash-out.

---

## 2. Existing functionality

| Area | Location | Status |
|------|----------|--------|
| Manual campaign paste + score | `packages/campaign_parser`, `routers/campaigns.py` | Working |
| Operator discover + top-3 approve | `routers/operator.py`, extension | Working (demo + fragile DOM) |
| Requirements store + snapshot | `CampaignRequirement.is_immutable_snapshot` | Working |
| Asset upload + process | `pipeline.py`, `tasks.py` | Working |
| Transcription | `workers/transcription` | Partial (WhisperX optional) |
| Scene detection | `workers/scene_detection` | Partial |
| Candidate rank 10–20 → top 3–5 | `tasks.py`, `clip_ranking` | Working (heuristic) |
| 3-account round-robin assign | `tasks.py` | Working |
| Style captions | `caption_generation` | Working |
| FFmpeg export packages | `video_rendering` | Partial (needs ffmpeg + file) |
| Remotion burn-in | `templates/` | Stub server only |
| Compliance checklist | `compliance_checker` | Working (some hardcodes) |
| Approval UI | `/review` | Partial (no video preview) |
| Posting assistant | `/queue`, `/exports` | Partial |
| Submission mark | `/tracking` | Working (manual) |
| Earnings + payout ready | pipeline + operator | Working |
| Learning cohorts | `clip_performance`, `analytics/learning` | Partial (no closed loop) |
| $1K home | `/` | Partial (USD; no forecast) |
| n8n | `workflows/n8n` | Stub |
| Tests | — | **None** |

---

## 3. Working functionality (verified by code + prior smoke)

- `POST /api/auth/login` JWT
- Campaign create/score; hard rejects (budget ≥90%, fake engagement, geo)
- Demo seed top-3; approve → creates `Campaign` + requirements
- Asset upload → analyse → candidates → versions → compliance
- Mark posted → `ClipPerformance` row; metrics/earnings/payout flow
- Operator notifications on discover/approve/brief/payout

---

## 4. Partially implemented

- WhisperX / PySceneDetect (optional deps; fallbacks always available)
- Scoring `factor_scores` computed but not exposed in API responses
- Production queue = `ProductionEvent` log, not full FSM recovery
- Analytics `/operator/analytics` hardcodes post views to 0
- Home “today” uses all-time post counts
- Extension DOM selectors are heuristic; CR layout changes break scan
- Remotion compositions exist; `/render` acknowledges without rendering
- Currency: planning target should be **£1,000**; code defaults USD `$`

---

## 5. Broken / bugs

| Issue | File |
|-------|------|
| `cpmMatch` used but never defined in scanner | `browser-extension/campaign-scanner/scanner.js` |
| n8n workflow has empty `connections` + invalid notify node type | `workflows/n8n/clipops-notify.json` |
| Postgres migration missing operator tables (`discovered_campaigns`, `clip_performance`, etc.) | `supabase/migrations/…` vs `db.py` |
| Compliance assumes logo/CTA/disclosure-in-video true | `tasks.py` |
| State transitions only enforced on approve | `pipeline.py` vs `ALLOWED_TRANSITIONS` |

---

## 6. TODOs / placeholders

- Heuristic transcript / scene windows when ML missing
- Empty `video.mp4` + `RENDER_ERROR.txt` on ffmpeg failure
- Unused `_run_module`, bcrypt helpers, `shutil` imports
- README claims ~85–90% automation; Remotion/n8n not production-ready

---

## 7. Missing dependencies

**API `requirements.txt`:** FastAPI stack only — no `whisperx`, `scenedetect`, `pytest`.  
**Dashboard:** no chart lib, no test runner.  
**Templates:** `render.js` referenced but missing.

---

## 8. Security issues

1. Default credentials `changeme` / weak JWT secret if `.env` not changed  
2. Plaintext password compare (bcrypt helpers unused)  
3. Uploads: no size/type allowlist; filename used in path  
4. JWT in `localStorage` + `chrome.storage.sync`  
5. CORS allows any `chrome-extension://` origin  
6. Compose Postgres `postgres:postgres`  
→ Mitigations planned: upload validation, document secret rotation, feature flags, no secrets in git (`.env` ignored)

---

## 9. Performance problems

- Sync Celery fallback blocks API on long WhisperX/ffmpeg jobs  
- Ranking all scenes with regex is cheap; rendering every candidate avoided (good — only top 3–5)  
- No pagination on some list endpoints  

---

## 10. Duplicate / dead code

- Dual campaign entry (manual `/campaigns` vs operator discover) — keep both  
- Dual scoring (`scoring.py` + `ranker.py` wrapper) — consolidate behind services  
- Unused Remotion service path from Python workers  

---

## 11. Missing tests

Zero unit/integration tests. Highest priority to add: scoring, compliance, ranking, forecast, state transitions, account assignment.

---

## 12. Recommended architecture (incremental)

1. **Services layer** (`packages/services/`):  
   `CampaignDiscoveryService`, `CampaignScoringService`, `ClipRankingService`, `PerformanceLearningService`, `ForecastService`
2. Keep FastAPI thin; workers unchanged contract  
3. SQLite for local; sync Postgres migration with ORM  
4. Browser-assisted discovery only (no unattended CR bot)  
5. Close learning loop: blend historical cohort lifts into campaign + clip scores when `n ≥ 50`  
6. Dashboard: £ target, forecast, review preview, regenerate  
7. Feature flags for Remotion burn-in and n8n webhooks  

---

## 13. Month-1 planning assumptions (not guarantees)

| Metric | Target |
|--------|--------|
| Accounts | 3 |
| Clips/day | 6–9 |
| Clips/month | ~180–270 |
| Approval rate | 70%+ |
| Planning CPM | £2 |
| Revenue target | ~£1,000 |

---

## 14. Audit conclusion → implementation priority

1. Write service layer + expose scoring explanations + forecast  
2. Fix extension bug; enrich clip ranking dimensions  
3. Account preferred length/hooks; £ dashboard + forecast UI  
4. Review regenerate + richer approval payload  
5. Unit tests + migration sync  
6. Valid n8n workflow stubs + docs (`IMPLEMENTATION_STATUS`, `USER_WORKFLOW`)  

**Audit complete. Implementation of highest-priority gaps follows.**
