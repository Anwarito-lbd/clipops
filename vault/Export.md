---
tags:
  - pipeline
---

# Export, Compliance Gate & Manual Publish

Upstream: [[Editing]], [[Remotion]] · Interactive Gate: [[OperatorUI]] · Back to [[Home]]

Implemented in `packages/compliance_checker/checker.py` (`run_compliance_check`) and `packages/shared_types/constants.py` (`ALLOWED_TRANSITIONS`).

## Ethical Automation Boundary

ClipOps is an editing and curation workstation — **not** an automated posting bot. `GET /health` reports `automation_boundary: human_approval_manual_posting` (and `human_approval_manual_publish` in [[OperatorUI]]). There is no state transition in `ALLOWED_TRANSITIONS` that posts to social platforms or submits claims autonomously:

- `REVIEW_REQUIRED` → `APPROVED` (or `REJECTED`)
- `APPROVED` → `EXPORTED`
- `EXPORTED` → `MANUALLY_POSTED` (only after the creator pastes their own published URL)
- `PAYOUT_READY` → `PAID`

## 12-Point Compliance Gate (`run_compliance_check`)

Before export, ClipOps checks: required hashtags, `@mentions`, disclosure text (e.g. `Paid partnership`), disclosure placement, `[min_duration_sec, max_duration_sec]` duration bounds, `9:16` aspect ratio, forbidden words/claims, external music flags, SHA-256 duplicate export hash (`assert_versions_not_identical` in `packages/posting_queue/router.py`), logo verification (fail-closed when `requires_logo=True` and `has_logo is None`), CTA presence, and deadline checks.

See [[EXAMPLES]] for observed compliance pass/fail outputs.
