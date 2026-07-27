"""Shared scoring constants for ClipOps Phase 1."""

PLATFORM_FEE_MULTIPLIER = 0.93
BUDGET_UTILISATION_REJECT_THRESHOLD = 0.90

SCORE_WEIGHTS = {
    "remaining_budget": 20,
    "cpm": 15,
    "audience_match": 20,
    "footage_quality": 15,
    "requirement_simplicity": 10,
    "viral_potential": 15,
    "competition": 5,
}

SEGMENT_SCORE_KEYS = [
    "strong_opening",
    "curiosity",
    "conflict_surprise",
    "emotional_reaction",
    "clear_payoff",
    "standalone_clarity",
    "campaign_relevance",
]

CLIP_STATUSES = [
    "IMPORTED",
    "ANALYSED",
    "GENERATED",
    "REVIEW_REQUIRED",
    "APPROVED",
    "EXPORTED",
    "MANUALLY_POSTED",
    "SUBMITTED",
    "UNDER_REVIEW",
    "ACCEPTED",
    "VALIDATING",
    "EARNING",
    "PAYOUT_READY",
    "PAID",
    "REJECTED",
    "FAILED",
]

ALLOWED_TRANSITIONS = {
    "IMPORTED": {"ANALYSED", "FAILED"},
    "ANALYSED": {"GENERATED", "FAILED"},
    "GENERATED": {"REVIEW_REQUIRED", "FAILED"},
    "REVIEW_REQUIRED": {"APPROVED", "REJECTED"},
    "APPROVED": {"EXPORTED", "REJECTED"},
    "EXPORTED": {"MANUALLY_POSTED"},
    "MANUALLY_POSTED": {"SUBMITTED"},
    "SUBMITTED": {"UNDER_REVIEW", "REJECTED"},
    "UNDER_REVIEW": {"ACCEPTED", "REJECTED"},
    "ACCEPTED": {"VALIDATING", "REJECTED"},
    "VALIDATING": {"EARNING", "REJECTED"},
    "EARNING": {"PAYOUT_READY"},
    "PAYOUT_READY": {"PAID"},
}

DURATION_BANDS = ["15-25", "25-40", "40-60"]
ACCOUNT_STYLES = ["dramatic", "educational", "commentary"]
