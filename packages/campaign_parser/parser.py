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
_CPM = re.compile(r"(?:cpm|reward\s*rate|per\s*1,?000)\D{0,20}\$?\s*([\d]+(?:\.\d+)?)", re.I)
_BUDGET = re.compile(r"(?:budget|total\s*budget)\D{0,20}\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m)?", re.I)
_UTILISED = re.compile(r"(?:utili[sz]ed|spent|used)\D{0,20}(\d{1,3})\s*%", re.I)
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

    cpm_m = _CPM.search(text)
    if cpm_m:
        parsed.cpm = float(cpm_m.group(1))

    budget_m = _BUDGET.search(text)
    if budget_m:
        parsed.total_budget = _scale_money(budget_m.group(1), budget_m.group(2))

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
    if "logo" in lower:
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
    parsed.raw_signals = {
        "line_count": len(lines),
        "char_count": len(text),
    }
    return parsed
