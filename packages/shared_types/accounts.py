"""Posting-account helpers — TikTok + YouTube (Content Rewards is identity-only)."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

POSTING_PLATFORMS = ("tiktok", "youtube")
PROMOTE_PLATFORMS = ("tiktok", "youtube", "twitter", "x")
CR_PLATFORM = "content_rewards"
ACCOUNT_STYLES = ("dramatic", "educational", "commentary")


def is_posting_platform(platform: str | None) -> bool:
    return (platform or "").lower() in POSTING_PLATFORMS


def open_url_for_platform(
    platform: str | None,
    *,
    tiktok_url: str,
    youtube_url: str,
    twitter_url: str = "https://x.com",
) -> str:
    p = (platform or "").lower()
    if p == "youtube":
        return youtube_url
    if p in {"twitter", "x"}:
        return twitter_url
    return tiktok_url


def account_label(account: Any) -> str:
    """Human label for queue / exports."""
    if getattr(account, "display_name", None):
        return str(account.display_name)
    platform = (getattr(account, "platform", None) or "social").capitalize()
    style = getattr(account, "style", None) or ""
    handle = getattr(account, "handle", None) or ""
    if style:
        return f"{platform} — {style.capitalize()} ({handle})"
    return f"{platform} — {handle}"


def slot_map_for_accounts(accounts: Sequence[Any]) -> dict[str, int]:
    """Stable 1-based slots for all posting accounts (supports 6+)."""
    return {a.id: i + 1 for i, a in enumerate(accounts)}


def posting_accounts_query_filter(SocialAccount: Any):
    """SQLAlchemy filter: active TikTok + YouTube accounts."""
    return (
        SocialAccount.platform.in_(list(POSTING_PLATFORMS)),
        SocialAccount.is_active.is_(True),
    )


def default_seed_rows() -> list[dict[str, Any]]:
    """Canonical seed: 1 CR identity + 3 TikTok + 3 YouTube."""
    rows: list[dict[str, Any]] = [
        {
            "platform": CR_PLATFORM,
            "handle": "operator",
            "display_name": "ClipOps CR Account",
            "style": None,
            "audience_geo": ["US", "CA"],
            "audience_notes": "Single Content Rewards identity — never duplicate",
            "preferred_clip_length": None,
            "preferred_hooks": [],
        },
    ]
    for style, length, hooks, notes in (
        ("dramatic", "15-25", ["drama", "question"], "Fast, dramatic clips"),
        ("educational", "25-40", ["surprising_fact", "question"], "Educational / storytelling"),
        ("commentary", "15-25", ["controversy", "question"], "Commentary, captions, reactions"),
    ):
        rows.append(
            {
                "platform": "tiktok",
                "handle": f"tiktok_{style}",
                "display_name": f"TikTok — {style.capitalize()}",
                "style": style,
                "audience_geo": ["US", "CA"],
                "audience_notes": notes,
                "preferred_clip_length": length,
                "preferred_hooks": hooks,
            }
        )
        rows.append(
            {
                "platform": "youtube",
                "handle": f"youtube_{style}",
                "display_name": f"YouTube — {style.capitalize()}",
                "style": style,
                "audience_geo": ["US", "CA"],
                "audience_notes": f"YouTube Shorts · {notes.lower()}",
                "preferred_clip_length": length,
                "preferred_hooks": hooks,
            }
        )
    # X/Twitter for affiliate promo (bio + scheduled pitches — not a posting-bot)
    rows.append(
        {
            "platform": "twitter",
            "handle": "twitter_affiliate",
            "display_name": "X — Affiliate promo",
            "style": "commentary",
            "audience_geo": ["US", "CA"],
            "audience_notes": "Affiliate pitches + bio link (you post; ClipOps reminds)",
            "preferred_clip_length": None,
            "preferred_hooks": [],
        }
    )
    return rows


def merge_audience_geos(accounts: Iterable[Any]) -> list[str]:
    geos: list[str] = []
    for a in accounts:
        geos.extend(getattr(a, "audience_geo", None) or [])
    return list(dict.fromkeys(geos)) or ["US", "CA"]
