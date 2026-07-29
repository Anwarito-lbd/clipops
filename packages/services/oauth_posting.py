"""Official OAuth posting stubs — TikTok Content Posting API + YouTube Data API.

These endpoints prepare OAuth connect flows. They do NOT implement unofficial
cookie bots. Direct public posting on TikTok requires app audit.
Cash-out on Content Rewards is never automated here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


def tiktok_authorize_url(*, client_key: str, redirect_uri: str, state: str = "clipops") -> str | None:
    if not client_key:
        return None
    params = {
        "client_key": client_key,
        "scope": "user.info.basic,video.upload,video.publish",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)


def youtube_authorize_url(*, client_id: str, redirect_uri: str, state: str = "clipops") -> str | None:
    if not client_id:
        return None
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def oauth_status(settings: Any) -> dict[str, Any]:
    return {
        "tiktok": {
            "configured": bool(getattr(settings, "tiktok_client_key", "")),
            "authorize_url": tiktok_authorize_url(
                client_key=getattr(settings, "tiktok_client_key", "") or "",
                redirect_uri=getattr(settings, "tiktok_redirect_uri", ""),
            ),
            "docs": "https://developers.tiktok.com/products/content-posting-api",
            "note": "App audit required for public Direct Post. Upload-to-inbox needs video.upload scope.",
        },
        "youtube": {
            "configured": bool(getattr(settings, "youtube_client_id", "")),
            "authorize_url": youtube_authorize_url(
                client_id=getattr(settings, "youtube_client_id", "") or "",
                redirect_uri=getattr(settings, "youtube_redirect_uri", ""),
            ),
            "docs": "https://developers.google.com/youtube/v3/docs/videos/insert",
            "note": "OAuth per YouTube channel. videos.insert uploads; you still confirm CR Submit.",
        },
        "content_rewards": {
            "auto_join": False,
            "auto_submit": False,
            "auto_cashout": False,
            "note": (
                "ClipOps never auto-Joins or cash-outs on Content Rewards. "
                "You get a notification when to Join / Cash out; the browser extension "
                "can highlight the button — you click it."
            ),
        },
        "forbidden": [
            "Scrapling StealthyFetcher CAPTCHA bypass against logged-in CR",
            "Unattended Playwright Join / Submit / Withdraw",
            "Unofficial TikTok/YouTube cookie upload bots",
        ],
    }
