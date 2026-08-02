"""Shared scoring constants for ClipOps Phase 1."""

PLATFORM_FEE_MULTIPLIER = 0.93
BUDGET_UTILISATION_REJECT_THRESHOLD = 0.90

# CPM that scores 100, on a square-root curve. Observed Content Rewards rates run
# $0.70–$10. A linear $15 ceiling squashed every real campaign into single digits;
# a linear $3 ceiling made $3 and $10 tie. The curve separates the low end (where
# most campaigns sit) while still rewarding a genuinely exceptional rate.
CPM_SCORE_CEILING = 10.0

# Marginal cash cost of producing one clip on your own hardware — electricity and
# wear, not your time. The old £15 default assumed paid tooling and made every
# campaign under ~$2.30 CPM look loss-making, which rejected most viable work.
DEFAULT_PRODUCTION_COST_PER_CLIP = 0.50

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
    "REVIEW_REQUIRED": {"APPROVED", "REJECTED", "REVIEW_REQUIRED"},
    "APPROVED": {"EXPORTED", "REJECTED", "FAILED", "REVIEW_REQUIRED"},
    "EXPORTED": {"MANUALLY_POSTED", "APPROVED", "REVIEW_REQUIRED"},
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
