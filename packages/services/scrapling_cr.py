"""Public Content Rewards campaign discovery via Scrapling (D4Vinci/Scrapling).

Uses HTTP ``Fetcher`` only — never StealthyFetcher CAPTCHA bypass, never
logged-in session cookies, never auto-Join / auto-Submit / auto cash-out.

Whop ToS prohibit scraping without written consent and ban automated engagement.
Treat this as optional research/ops assist for *public* discover pages; Join and
cash-out remain human gates (ClipOps notifies you).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

DEFAULT_DISCOVER_URL = "https://whop.com/discover/content-rewards/"


def _parse_money(text: str) -> float | None:
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_pct(text: str) -> float | None:
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_scraped_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a scraped card into ClipOps DiscoveredItem-shaped dict."""
    name = (raw.get("name") or raw.get("title") or "Unknown campaign").strip()
    cpm = raw.get("cpm")
    if cpm is None and raw.get("reward_text"):
        cpm = _parse_money(str(raw["reward_text"]))
    budget_left_pct = raw.get("budget_remaining_pct")
    if budget_left_pct is None and raw.get("budget_text"):
        # Prefer explicit remaining %; else invert spent %
        spent = _parse_pct(str(raw["budget_text"]))
        if spent is not None and "spent" in str(raw["budget_text"]).lower():
            budget_left_pct = max(0.0, 100.0 - spent)
        else:
            budget_left_pct = _parse_pct(str(raw["budget_text"]))
    external_url = raw.get("external_url") or raw.get("url")
    return {
        "external_id": raw.get("external_id") or raw.get("id"),
        "external_url": external_url,
        "name": name,
        "brand": raw.get("brand"),
        "cpm": cpm,
        "budget_remaining_pct": budget_left_pct,
        "required_clips": int(raw.get("required_clips") or 3),
        "min_duration_sec": int(raw.get("min_duration_sec") or 15),
        "max_duration_sec": int(raw.get("max_duration_sec") or 60),
        "required_hashtags": list(raw.get("required_hashtags") or []),
        "required_tags": list(raw.get("required_tags") or []),
        "required_disclosure": raw.get("required_disclosure"),
        "required_geo": list(raw.get("required_geo") or []),
        "has_rights": bool(raw.get("has_rights", True)),
        "brief_text": raw.get("brief_text") or raw.get("description"),
        "asset_urls": list(raw.get("asset_urls") or []),
        "raw": raw,
    }


def parse_discover_html(html: str, *, base_url: str = DEFAULT_DISCOVER_URL) -> list[dict[str, Any]]:
    """Best-effort parse of public discover HTML without Scrapling installed.

    Site markup drifts often — adaptive Scrapling CSS is preferred when available.
    """
    items: list[dict[str, Any]] = []
    # Anchor cards that look like campaign links
    for m in re.finditer(
        r'href="([^"]*(?:content-rewards|campaigns?)[^"]*)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        href, inner = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        inner = re.sub(r"\s+", " ", inner).strip()
        if len(inner) < 3:
            continue
        url = urljoin(base_url, href)
        items.append(
            normalize_scraped_item(
                {
                    "name": inner[:120],
                    "external_url": url,
                    "external_id": href.rstrip("/").split("/")[-1],
                    "brief_text": inner[:500],
                }
            )
        )
    # Dedupe by URL
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        key = it.get("external_url") or it.get("name") or ""
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out[:50]


def scrape_with_scrapling(url: str) -> list[dict[str, Any]]:
    """Fetch public discover page with Scrapling Fetcher and extract cards."""
    from scrapling.fetchers import Fetcher

    page = Fetcher.get(url, stealthy_headers=True)
    html = getattr(page, "html_content", None) or getattr(page, "body", None) or str(page)
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")

    items: list[dict[str, Any]] = []
    # Adaptive CSS — survives minor markup changes when auto_save/adaptive used over time
    cards = []
    try:
        cards = page.css("a[href*='content-rewards'], a[href*='campaign']")
    except Exception:
        cards = []
    for card in cards or []:
        try:
            href = card.attrib.get("href") if hasattr(card, "attrib") else None
            if not href:
                href = card.css("::attr(href)").get() if hasattr(card, "css") else None
            text = ""
            if hasattr(card, "get_all_text"):
                text = card.get_all_text(separator=" ")
            elif hasattr(card, "css"):
                text = " ".join(card.css("::text").getall() or [])
            else:
                text = str(card)
            text = re.sub(r"\s+", " ", text or "").strip()
            if not href or len(text) < 3:
                continue
            full = urljoin(url, href)
            reward = None
            for node_text in [text]:
                if "/1k" in node_text.lower() or "cpm" in node_text.lower() or "$" in node_text:
                    reward = node_text
            items.append(
                normalize_scraped_item(
                    {
                        "name": text[:120],
                        "external_url": full,
                        "external_id": href.rstrip("/").split("/")[-1],
                        "reward_text": reward,
                        "brief_text": text[:500],
                    }
                )
            )
        except Exception:
            continue

    if not items and html:
        items = parse_discover_html(html, base_url=url)

    # Dedupe
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        key = it.get("external_url") or it.get("name") or ""
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out[:50]


def discover_public_campaigns(
    *,
    url: str | None = None,
    use_scrapling: bool = True,
) -> dict[str, Any]:
    """Return ``{campaigns, source, note, error?}`` for ClipOps ingest."""
    target = url or DEFAULT_DISCOVER_URL
    note = (
        "Public discover scrape only. ClipOps will NOT auto-Join or cash-out. "
        "You confirm Join / Post / Submit / Cash-out. "
        "Whop ToS disallow scraping without written consent — use at your own risk."
    )
    if use_scrapling:
        try:
            campaigns = scrape_with_scrapling(target)
            return {
                "campaigns": campaigns,
                "source": "scrapling",
                "url": target,
                "note": note,
                "count": len(campaigns),
            }
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            return {
                "campaigns": [],
                "source": "scrapling_error",
                "url": target,
                "note": note,
                "count": 0,
                "error": str(exc),
            }

    # Fallback: httpx + regex parser (tests / no scrapling)
    try:
        import httpx

        resp = httpx.get(target, follow_redirects=True, timeout=30.0)
        campaigns = parse_discover_html(resp.text, base_url=str(resp.url))
        return {
            "campaigns": campaigns,
            "source": "httpx_fallback",
            "url": target,
            "note": note,
            "count": len(campaigns),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "campaigns": [],
            "source": "httpx_error",
            "url": target,
            "note": note,
            "count": 0,
            "error": str(exc),
        }
