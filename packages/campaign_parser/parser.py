"""Parse pasted Content Rewards campaign briefs into structured fields."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ParsedBrief:
    name: str = "Untitled campaign"
    brand: str | None = None
    cpm: float | None = None
    total_budget: float | None = None
    budget_utilised: float | None = None
    max_payout: float | None = None
    required_geo: list[str] = field(default_factory=list)
    required_hashtags: list[str] = field(default_factory=list)
    required_tags: list[str] = field(default_factory=list)
    required_disclosure: str | None = "Paid partnership / Content Rewards"
    min_duration_sec: int = 15
    max_duration_sec: int = 60
    forbidden_words: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    requires_logo: bool = False
    requires_cta: bool = False
    cta_text: str | None = None
    has_rights: bool = True
    unclear_instructions: bool = False
    requires_fake_engagement: bool = False
    misleading_content: bool = False
    eligibility: dict[str, Any] = field(default_factory=dict)
    raw_signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m)?", re.I)

# CPM patterns, most specific first. The amount must be adjacent to the keyword —
# never "keyword ... <prose> ... number", which used to capture the first stray
# figure in the body text (e.g. "$2 CPM ... August 25th launch" -> 25).
_CPM_PATTERNS = (
    # "$2 CPM", "$0.70 CPM", "$2/CPM"
    re.compile(r"[\$£€]\s*([\d]+(?:\.\d+)?)\s*(?:/|per\s+)?\s*CPM\b", re.I),
    # "$1/1K", "$2 per 1,000", "$2 per 1k views". The denominator must be an
    # explicit 1000/1K — a bare "1" matches typos like "earn $4 per 1 views".
    re.compile(r"[\$£€]\s*([\d]+(?:\.\d+)?)\s*(?:/|per\s+)\s*(?:1[,.]?000|1\s*k)\b", re.I),
    # "CPM: $2", "CPM of $2" — number after, but only across an explicit separator
    re.compile(r"\bCPM\b\s*(?:of|is|:|=|-)\s*[\$£€]?\s*([\d]+(?:\.\d+)?)", re.I),
    # "reward rate: $2"
    re.compile(r"reward\s*rate\s*(?:of|is|:|=|-)\s*[\$£€]?\s*([\d]+(?:\.\d+)?)", re.I),
)

# "$658/$10,000" — the progress display. Most reliable source of both figures.
_BUDGET_PROGRESS = re.compile(
    r"[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*/\s*[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?",
    re.I,
)

_BUDGET_PATTERNS = (
    # "$10,000 budget", "$10k Budget", "500€ Budget"
    re.compile(r"[\$£€]?\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*[\$£€]?\s*(?:total\s+)?budget\b", re.I),
    # "Budget: $10k", "Budget of $5K"
    re.compile(r"\bbudget\b\s*(?:of|is|:|=|-)\s*[\$£€]?\s*([\d,]+(?:\.\d+)?)\s*([km])?", re.I),
)

_UTILISED = re.compile(r"(?:utili[sz]ed|spent|used)\D{0,20}(\d{1,3})\s*%", re.I)

# Per-clipper payout cap. Content Rewards limits how much any one clipper can
# take from a campaign, so this — not CPM — is what bounds a campaign's worth.
_MAX_PAYOUT_PATTERNS = (
    # "max payout $500", "maximum payout: $500", "payout cap $500"
    re.compile(
        r"(?:max(?:imum)?|cap(?:ped)?)\s*(?:payout|payment|earnings?)\s*(?:per\s*\w+\s*)?"
        r"(?:of|is|:|=|-|at)?\s*[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?",
        re.I,
    ),
    # "payout capped at $500", "earnings capped at $500"
    re.compile(
        r"(?:payout|payment|earnings?)\s*(?:is\s*)?cap(?:ped)?\s*(?:at|to)\s*"
        r"[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?",
        re.I,
    ),
    # "up to $500 per clipper/creator/person/account"
    re.compile(
        r"up\s*to\s*[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*per\s*"
        r"(?:clipper|creator|person|account|user|participant)",
        re.I,
    ),
    # "$500 max per clipper", "$500 maximum per creator"
    re.compile(
        r"[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*(?:max(?:imum)?|cap)\s*per\s*"
        r"(?:clipper|creator|person|account|user|participant)",
        re.I,
    ),
    # "max $500 per clipper"
    re.compile(
        r"max(?:imum)?\s*[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*per\s*"
        r"(?:clipper|creator|person|account|user|participant)",
        re.I,
    ),
)

# A CPM outside this range is a parse artifact, not a real rate. Content Rewards
# rates sit around $0.10–$10; 658 came from reading a payout figure as a rate.
_CPM_MAX = 100.0


def extract_max_payout(text: str) -> float | None:
    """Per-clipper payout cap, or None when the brief doesn't state one."""
    for pattern in _MAX_PAYOUT_PATTERNS:
        m = pattern.search(text)
        if m:
            value = _scale_money(m.group(1), m.group(2))
            if value > 0:
                return value
    return None


def extract_cpm(text: str) -> float | None:
    """Return the campaign CPM, or None when no pattern matches confidently."""
    for pattern in _CPM_PATTERNS:
        m = pattern.search(text)
        if m:
            value = float(m.group(1))
            if 0 < value <= _CPM_MAX:
                return value
    return None


def distinct_rates(text: str) -> list[float]:
    """Every distinct rate mentioned in the text.

    More than one means the scraper merged several campaign cards into a single
    blob, so no figure in it can be attributed to a particular campaign.
    """
    found: list[float] = []
    for pattern in _CPM_PATTERNS:
        for m in pattern.finditer(text):
            value = float(m.group(1))
            if 0 < value <= _CPM_MAX and value not in found:
                found.append(value)
    return sorted(found)


def looks_like_multiple_campaigns(text: str) -> bool:
    """True when a single scraped card appears to hold more than one campaign."""
    if len(distinct_rates(text)) > 1:
        return True
    # Several "Join Campaign" buttons in one blob is the other tell.
    return len(re.findall(r"join\s+campaign", text, re.I)) > 1


def extract_budget(text: str) -> tuple[float | None, float | None]:
    """Return (total_budget, budget_utilised). Either may be None."""
    prog = _BUDGET_PROGRESS.search(text)
    if prog:
        used = _scale_money(prog.group(1), prog.group(2))
        total = _scale_money(prog.group(3), prog.group(4))
        if total > 0 and used <= total:
            return total, used
    for pattern in _BUDGET_PATTERNS:
        m = pattern.search(text)
        if m:
            total = _scale_money(m.group(1), m.group(2))
            if total > 0:
                return total, None
    return None, None
_HASHTAG = re.compile(r"#[A-Za-z0-9_]+")
_GEO = re.compile(
    r"\b(US|USA|United States|CA|Canada|UK|GB|AU|Australia|EU|JP|Japan|DE|FR|MX|BR|IN)\b",
    re.I,
)
_DURATION = re.compile(r"(\d+)\s*[-–to]+\s*(\d+)\s*(?:s|sec|seconds)", re.I)


def _scale_money(num: str, suffix: str | None) -> float:
    value = float(num.replace(",", ""))
    if not suffix:
        return value
    s = suffix.lower()
    if s == "k":
        return value * 1_000
    if s == "m":
        return value * 1_000_000
    return value


def parse_campaign_brief(raw: str) -> ParsedBrief:
    text = (raw or "").strip()
    parsed = ParsedBrief()
    if not text:
        parsed.unclear_instructions = True
        return parsed

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # First non-empty line as name if short enough
    if lines and len(lines[0]) <= 120:
        parsed.name = lines[0]
    brand_match = re.search(r"(?:brand|advertiser)\s*[:\-]\s*(.+)", text, re.I)
    if brand_match:
        parsed.brand = brand_match.group(1).strip()[:120]

    # A blob holding several campaigns can't have its figures attributed to any
    # one of them — better to report nothing than the wrong campaign's numbers.
    if looks_like_multiple_campaigns(text):
        parsed.unclear_instructions = True
        parsed.raw_signals["multiple_campaigns_in_card"] = True
        parsed.raw_signals["rates_seen"] = distinct_rates(text)
    else:
        parsed.cpm = extract_cpm(text)
        parsed.total_budget, parsed.budget_utilised = extract_budget(text)
        parsed.max_payout = extract_max_payout(text)

    if parsed.budget_utilised is None:
        util_m = _UTILISED.search(text)
        if util_m and parsed.total_budget:
            pct = float(util_m.group(1)) / 100.0
            parsed.budget_utilised = round(parsed.total_budget * pct, 2)

    parsed.required_hashtags = list(dict.fromkeys(_HASHTAG.findall(text)))
    geos = []
    for g in _GEO.findall(text):
        g_up = g.upper()
        if g_up in {"USA", "UNITED STATES"}:
            g_up = "US"
        if g_up in {"UNITED KINGDOM", "GB"}:
            g_up = "UK"
        if g_up == "JAPAN":
            g_up = "JP"
        geos.append(g_up)
    parsed.required_geo = list(dict.fromkeys(geos))

    dur = _DURATION.search(text)
    if dur:
        parsed.min_duration_sec = int(dur.group(1))
        parsed.max_duration_sec = int(dur.group(2))

    lower = text.lower()
    # The bare word "logo" appears in plenty of briefs that don't mandate one —
    # require an actual obligation.
    if re.search(r"logo\s+(?:is\s+)?(?:required|mandatory|must)|must\s+(?:include|show|display|feature)\s+(?:the\s+)?logo|include\s+(?:the\s+)?logo", lower):
        parsed.requires_logo = True
    if re.search(r"\bcta\b|call to action|link in bio", lower):
        parsed.requires_cta = True
        cta_m = re.search(r"(?:cta|call to action)\s*[:\-]\s*(.+)", text, re.I)
        if cta_m:
            parsed.cta_text = cta_m.group(1).strip()[:200]

    if re.search(r"no rights|do not have rights|unlicensed", lower):
        parsed.has_rights = False

    if re.search(r"buy followers|fake (views|likes|engagement)|bot views|misleading", lower):
        parsed.requires_fake_engagement = True
        if "misleading" in lower:
            parsed.misleading_content = True

    # Heuristic: contradictory duration or missing both CPM and budget
    if parsed.min_duration_sec > parsed.max_duration_sec:
        parsed.unclear_instructions = True
    if parsed.cpm is None and parsed.total_budget is None and len(text) < 80:
        parsed.unclear_instructions = True

    tag_m = re.findall(r"@([A-Za-z0-9._]+)", text)
    parsed.required_tags = list(dict.fromkeys(f"@{t}" for t in tag_m))

    disc = re.search(r"(?:disclosure|disclose)\s*[:\-]\s*(.+)", text, re.I)
    if disc:
        parsed.required_disclosure = disc.group(1).strip()[:300]

    parsed.eligibility = {
        "min_age": 18,
        "notes": "Ages 13–17 must use verified parent/guardian CR account",
    }
    parsed.raw_signals.update(
        {
            "line_count": len(lines),
            "char_count": len(text),
        }
    )
    return parsed
