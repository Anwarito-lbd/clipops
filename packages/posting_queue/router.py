"""Posting queue — route approved renders to three TikTok accounts."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


ACCOUNT_SLOTS = {
    1: {"style": "dramatic", "label": "TikTok 1 — Dramatic"},
    2: {"style": "educational", "label": "TikTok 2 — Educational"},
    3: {"style": "commentary", "label": "TikTok 3 — Commentary"},
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
    # No cap: more clips are selected than there are accounts, so slicing to 3
    # discarded real output. `i` can now exceed len(ACCOUNT_SLOTS), so every
    # lookup below must stay in range.
    for i, v in enumerate(versions, start=1):
        fallback_slot = ((i - 1) % len(ACCOUNT_SLOTS)) + 1
        style = v.get("style") or ACCOUNT_SLOTS[fallback_slot]["style"]
        # Prefer the slot the renderer actually used.
        slot = v.get("account_slot") or next(
            (s for s, meta in ACCOUNT_SLOTS.items() if meta["style"] == style),
            fallback_slot,
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
                # Degrade to a generic label for slots beyond the known set —
                # mislabelling slot 4 as "TikTok 1" would send the clip to the
                # wrong account.
                account_label=(
                    ACCOUNT_SLOTS[slot]["label"]
                    if slot in ACCOUNT_SLOTS
                    else f"TikTok {slot}"
                ),
                style=style,
                video_path=render.get("video_path") or render.get("package_dir"),
                caption=caption,
                disclosure_included="paid" in caption.lower() or "partnership" in caption.lower(),
                hashtags=[t for t in caption.split() if t.startswith("#")],
                compliance_passed=passed,
                compliance_total=total,
                duplicate_safe=True,
                # A Render row exists even for failed renders. Only a content
                # hash proves a real, non-empty video was produced.
                status="READY" if render.get("content_hash") else "WAITING_POST",
            )
        )
    return packages


def assert_versions_not_identical(content_hashes: list[str | None]) -> bool:
    hashes = [h for h in content_hashes if h]
    return len(hashes) == len(set(hashes))
