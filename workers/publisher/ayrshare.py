"""Ayrshare: one API that posts to YouTube, TikTok and Instagram through its already-audited apps.

Use it for public posting on launch day while your own YouTube/TikTok API audits are pending.
Setup: ayrshare.com account -> link your YouTube, TikTok and Instagram in their dashboard
(one *User Profile* per posting account on Business plans) -> set AYRSHARE_API_KEY and,
per account, a Profile Key env var named in accounts.json.

Verify on first run with `python -m workers.publisher post <clip_dir> --account A --dry-run`
then one real post to a test profile: endpoint/field names follow Ayrshare's public docs.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from .base import PostRequest, PostResult, http

API = "https://api.ayrshare.com/api"


class AyrsharePublisher:
    """Posts one clip to several platforms in a single call; returns one PostResult per platform."""

    def __init__(self, *, api_key: str | None = None, profile_key: str | None = None, opener=None):
        self.api_key = api_key or os.environ.get("AYRSHARE_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("set AYRSHARE_API_KEY")
        self.profile_key = profile_key
        self.kw = {"opener": opener} if opener else {}

    def _headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"}
        if self.profile_key:
            h["Profile-Key"] = self.profile_key
        return h

    def _upload(self, path: str) -> str:
        name = Path(path).name
        q = urllib.parse.urlencode({"fileName": name, "contentType": "mp4"})
        _, _, res = http("GET", f"{API}/media/uploadUrl?{q}", headers=self._headers(), **self.kw)
        upload_url, access_url = res.get("uploadUrl"), res.get("accessUrl")
        if not (upload_url and access_url):
            raise RuntimeError(f"Ayrshare uploadUrl response missing fields: {res}")
        http("PUT", upload_url, data=Path(path).read_bytes(), timeout=600,
             headers={"Content-Type": res.get("contentType") or "video/mp4"}, **self.kw)
        return access_url

    def publish_many(self, req: PostRequest, platforms: list[str]) -> list[PostResult]:
        media = self._upload(req.video_path)
        body = {
            "post": req.caption[:2200],
            "platforms": platforms,
            "mediaUrls": [media],
            "isVideo": True,
            "youTubeOptions": {"title": req.title[:100], "visibility": "public", "shorts": True},
            "instagramOptions": {"shareReelsFeed": True},
        }
        _, _, res = http("POST", f"{API}/post", json_body=body, headers=self._headers(), timeout=300, **self.kw)
        by_platform = {p.get("platform"): p for p in (res.get("postIds") or [])}
        errors = {e.get("platform"): e for e in (res.get("errors") or []) if isinstance(e, dict)}
        out = []
        for plat in platforms:
            got = by_platform.get(plat)
            if got and got.get("status", "success") == "success":
                out.append(PostResult(plat, True, post_id=str(got.get("id") or ""), url=got.get("postUrl"),
                                      visibility="public", via="ayrshare", detail={"ayrshare_id": res.get("id")}))
            else:
                err = errors.get(plat) or {"message": res.get("message") or res.get("status") or "no post id"}
                out.append(PostResult(plat, False, via="ayrshare", error=str(err.get("message") or err)))
        return out
