"""Pre-approval compliance checks for ClipOps exports."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class CheckItem:
    key: str
    label: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComplianceResult:
    passed: bool
    checks: list[CheckItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
        }


def run_compliance_check(
    *,
    campaign_name: str,
    expected_campaign_name: str,
    caption: str,
    required_hashtags: list[str],
    required_tags: list[str],
    required_disclosure: str | None,
    disclosure_in_video_start: bool,
    duration_sec: float,
    min_duration_sec: int,
    max_duration_sec: int,
    aspect_ratio: str,
    expected_aspect_ratio: str = "9:16",
    forbidden_words: list[str],
    forbidden_claims: list[str],
    has_external_music: bool,
    export_hash: str | None,
    existing_hashes: list[str],
    requires_logo: bool,
    has_logo: bool,
    requires_cta: bool,
    has_cta: bool,
    posting_deadline: datetime | None,
    misleading_caption: bool = False,
) -> ComplianceResult:
    checks: list[CheckItem] = []

    def add(key: str, label: str, passed: bool, detail: str = "") -> None:
        checks.append(CheckItem(key=key, label=label, passed=passed, detail=detail))

    add(
        "campaign_name",
        "Correct campaign name",
        campaign_name.strip().lower() == expected_campaign_name.strip().lower(),
        f"got={campaign_name!r} expected={expected_campaign_name!r}",
    )

    missing_tags = [h for h in required_hashtags if h.lower() not in caption.lower()]
    add(
        "hashtags",
        "Required hashtags",
        len(missing_tags) == 0,
        f"missing={missing_tags}",
    )

    missing_mentions = [t for t in required_tags if t.lower() not in caption.lower()]
    add(
        "account_tags",
        "Required account tags",
        len(missing_mentions) == 0,
        f"missing={missing_mentions}",
    )

    disclosure_ok = True
    if required_disclosure:
        disclosure_ok = (
            required_disclosure.lower() in caption.lower() or disclosure_in_video_start
        )
    add(
        "disclosure",
        "Required disclosure at beginning",
        disclosure_ok and (disclosure_in_video_start if required_disclosure else True),
        "Paid-content disclosure must be clear, conspicuous, and at video start",
    )

    add(
        "duration",
        "Correct video length",
        min_duration_sec <= duration_sec <= max_duration_sec,
        f"{duration_sec}s not in [{min_duration_sec}, {max_duration_sec}]",
    )

    add(
        "aspect_ratio",
        "Correct aspect ratio",
        aspect_ratio == expected_aspect_ratio,
        f"got={aspect_ratio} expected={expected_aspect_ratio}",
    )

    caption_l = caption.lower()
    hit_words = [w for w in forbidden_words if w.lower() in caption_l]
    hit_claims = [c for c in forbidden_claims if c.lower() in caption_l]
    add(
        "forbidden",
        "No forbidden words or claims",
        not hit_words and not hit_claims,
        f"words={hit_words} claims={hit_claims}",
    )

    add(
        "external_music",
        "No copyrighted external music",
        not has_external_music,
        "Flagged external music — use campaign-approved audio only",
    )

    dup = bool(export_hash and export_hash in existing_hashes)
    add(
        "duplicate_export",
        "No duplicated export",
        not dup,
        "Identical asset hash already exported — meaningfully change each account version",
    )

    add(
        "misleading_caption",
        "No misleading captions",
        not misleading_caption,
    )

    add(
        "logo",
        "Campaign logo present when required",
        (has_logo if requires_logo else True),
    )
    add(
        "cta",
        "Campaign CTA present when required",
        (has_cta if requires_cta else True),
    )

    deadline_ok = True
    if posting_deadline is not None:
        now = datetime.now(timezone.utc)
        dl = posting_deadline if posting_deadline.tzinfo else posting_deadline.replace(tzinfo=timezone.utc)
        deadline_ok = now <= dl
    add("deadline", "Correct posting deadline", deadline_ok)

    return ComplianceResult(passed=all(c.passed for c in checks), checks=checks)
