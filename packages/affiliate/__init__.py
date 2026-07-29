"""Affiliate marketing helpers inspired by MoneyPrinterV2 — ClipOps-safe subset.

Borrowed ideas (https://github.com/FujiwaraChoki/MoneyPrinterV2):
- Amazon affiliate tag + product pitches
- Bio lines that include affiliate links
- Scheduled *reminders* to promote affiliates

NOT implemented (ToS / spam):
- Firefox browser bots that auto-tweet / auto-upload Shorts
- Scraping Amazon at scale without permission
- Local-business scrape + cold email outreach
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


@dataclass
class AffiliatePitch:
    title: str
    body: str
    affiliate_url: str
    platform: str  # twitter | tiktok | youtube
    hashtags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_amazon_tag(product_url: str, tag: str) -> str:
    """Append or replace Amazon affiliate tag= on a product URL."""
    if not product_url or not tag:
        return product_url or ""
    parsed = urlparse(product_url.strip())
    qs = parse_qs(parsed.query)
    qs["tag"] = [tag]
    # flatten
    flat = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in qs.items()}
    return urlunparse(parsed._replace(query=urlencode(flat)))


def build_bio(
    *,
    display_name: str,
    niche: str,
    affiliate_url: str | None,
    platform: str,
    extra_line: str | None = None,
) -> str:
    """Short bio text the operator pastes into TikTok / YouTube / X."""
    lines = [
        display_name.strip() or "Creator",
        (niche or "Daily clips & finds").strip()[:80],
    ]
    if affiliate_url:
        if platform in {"twitter", "x"}:
            lines.append(f"Shop: {affiliate_url}")
        elif platform == "youtube":
            lines.append(f"Links & deals: {affiliate_url}")
        else:
            lines.append(f"🔗 {affiliate_url}")
    if extra_line:
        lines.append(extra_line.strip()[:80])
    # Platform bio length soft caps
    text = " | ".join(lines) if platform in {"twitter", "x"} else "\n".join(lines)
    if platform in {"twitter", "x"}:
        return text[:160]
    if platform == "tiktok":
        return text[:80]
    return text[:1000]


def generate_pitch(
    *,
    product_name: str,
    product_url: str,
    talking_points: list[str] | None = None,
    platform: str = "twitter",
    disclosure: str = "Ad / affiliate link",
) -> AffiliatePitch:
    """Template pitch (no LLM required). Operator reviews then posts."""
    points = talking_points or ["solid pick", "worth a look"]
    bullet = "; ".join(p.strip() for p in points[:3] if p.strip())
    if platform in {"twitter", "x"}:
        body = (
            f"{product_name} — {bullet}.\n"
            f"{disclosure}\n"
            f"{product_url}"
        )
        # soft tweet length
        if len(body) > 280:
            body = f"{product_name} — {points[0]}. {disclosure}\n{product_url}"[:280]
        hashtags = ["#ad", "#affiliate"]
    elif platform == "youtube":
        body = (
            f"{disclosure}\n\n"
            f"Check out {product_name}: {product_url}\n"
            f"Why I like it: {bullet}"
        )
        hashtags = ["#shorts", "#ad"]
    else:  # tiktok caption
        body = f"{product_name} 👀 {bullet}\n{disclosure}\n{product_url}"
        hashtags = ["#fyp", "#ad"]
    return AffiliatePitch(
        title=product_name,
        body=body,
        affiliate_url=product_url,
        platform=platform,
        hashtags=hashtags,
    )


def next_cron_slots(
    *,
    times_per_day: int = 2,
    now: datetime | None = None,
) -> list[str]:
    """Suggested UTC HH:MM slots (MoneyPrinterV2 CRON idea — notify only)."""
    times_per_day = max(1, min(6, int(times_per_day)))
    _ = now or datetime.now(timezone.utc)
    # Spread across waking hours 14–22 UTC as defaults
    hours = [14, 17, 20, 12, 19, 22][:times_per_day]
    return [f"{h:02d}:00" for h in hours]


def should_notify_now(
    *,
    times_per_day: int,
    last_notified_at: datetime | None,
    now: datetime | None = None,
    force: bool = False,
) -> bool:
    """Cooldown gate so run-due does not spam when called often from cron."""
    if force:
        return True
    times_per_day = max(1, min(6, int(times_per_day)))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if last_notified_at is None:
        return True
    last = last_notified_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    min_gap_hours = 24.0 / times_per_day
    elapsed = (current - last).total_seconds() / 3600.0
    return elapsed >= min_gap_hours
