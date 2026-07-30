"""Posting queue — route approved renders to linked TikTok + YouTube accounts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PostingPackage:
    campaign_id: str
    clip_version_id: str
    account_slot: int
    account_label: str
    platform: str
    social_account_id: str | None
    style: str
    video_path: str | None
    caption: str
    disclosure_included: bool
    hashtags: list[str]
    compliance_passed: int
    compliance_total: int
    duplicate_safe: bool
    status: str  # READY | WAITING_POST | POSTED | SUBMIT_READY | SUBMITTED
    open_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_posting_packages(
    versions: list[dict[str, Any]],
    renders: list[dict[str, Any]],
    compliance_by_version: dict[str, dict[str, Any]],
    *,
    account_meta: dict[str, dict[str, Any]] | None = None,
    default_open_url: str = "https://www.tiktok.com",
) -> list[PostingPackage]:
    """Map account versions into an operator posting queue.

    ``account_meta`` maps social_account_id → {slot, label, platform, open_url}.
    When omitted, falls back to style-based slots (legacy 3-TikTok behaviour).
    """
    render_by_version = {r["clip_version_id"]: r for r in renders}
    meta = account_meta or {}
    packages: list[PostingPackage] = []
    for i, v in enumerate(versions, start=1):
        account_id = v.get("social_account_id")
        info = meta.get(account_id or "", {})
        style = v.get("style") or info.get("style") or "dramatic"
        platform = (v.get("platform") or info.get("platform") or "tiktok").lower()
        slot = int(info.get("slot") or v.get("account_slot") or i)
        label = info.get("label") or v.get("account_label") or f"{platform.capitalize()} — {style}"
        open_url = info.get("open_url") or default_open_url
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
                account_label=label,
                platform=platform,
                social_account_id=account_id,
                style=style,
                video_path=render.get("video_path") or render.get("package_dir"),
                caption=caption,
                disclosure_included="paid" in caption.lower() or "partnership" in caption.lower(),
                hashtags=[t for t in caption.split() if t.startswith("#")],
                compliance_passed=passed,
                compliance_total=total,
                duplicate_safe=True,
                status="READY" if render else "WAITING_POST",
                open_url=open_url,
            )
        )
    return packages


def assert_versions_not_identical(content_hashes: list[str | None]) -> bool:
    hashes = [h for h in content_hashes if h]
    return len(hashes) == len(set(hashes))
