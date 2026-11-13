"""Export queue — route approved renders across three editorial style channels."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


ACCOUNT_SLOTS = {
    1: {"style": "dramatic", "label": "Channel 1 — Dramatic Cut"},
    2: {"style": "educational", "label": "Channel 2 — Educational Cut"},
    3: {"style": "commentary", "label": "Channel 3 — Commentary Cut"},
}


@dataclass
class PostingPackage:
    campaign_id: str
    clip_version_id: str
    account_slot: int
    account_label: str
    style: str
    video_path: str | None
    caption: str
    disclosure_included: bool
    hashtags: list[str]
    compliance_passed: int
    compliance_total: int
    duplicate_safe: bool
    status: str  # READY | WAITING_POST | POSTED | SUBMIT_READY | SUBMITTED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_posting_packages(
    versions: list[dict[str, Any]],
    renders: list[dict[str, Any]],
    compliance_by_version: dict[str, dict[str, Any]],
) -> list[PostingPackage]:
    """Map three account versions into an operator posting queue."""
    render_by_version = {r["clip_version_id"]: r for r in renders}
    packages: list[PostingPackage] = []
    for i, v in enumerate(versions[:3], start=1):
        style = v.get("style") or ACCOUNT_SLOTS[i]["style"]
        slot = next(
            (s for s, meta in ACCOUNT_SLOTS.items() if meta["style"] == style),
            i,
        )
        render = render_by_version.get(v["id"], {})
        comp = compliance_by_version.get(v["id"], {})
        checks = comp.get("checks") or []
        passed = sum(1 for c in checks if c.get("passed"))
        total = len(checks) or 12
        caption = v.get("caption") or ""
        packages.append(
            PostingPackage(
                campaign_id=v.get("campaign_id", ""),
                clip_version_id=v["id"],
                account_slot=slot,
                account_label=ACCOUNT_SLOTS.get(slot, ACCOUNT_SLOTS[1])["label"],
                style=style,
                video_path=render.get("video_path") or render.get("package_dir"),
                caption=caption,
                disclosure_included="paid" in caption.lower() or "partnership" in caption.lower(),
                hashtags=[t for t in caption.split() if t.startswith("#")],
                compliance_passed=passed,
                compliance_total=total,
                duplicate_safe=True,
                status="READY" if render else "WAITING_POST",
            )
        )
    return packages


def assert_versions_not_identical(content_hashes: list[str | None]) -> bool:
    hashes = [h for h in content_hashes if h]
    return len(hashes) == len(set(hashes))
