"""TikTok upload via the official Content Posting API (Direct Post, FILE_UPLOAD).

Setup (once): developers.tiktok.com -> create app -> add Login Kit + Content Posting API
(Direct Post) -> scopes `user.info.basic`, `video.publish` -> register a redirect URI ->
`python -m workers.publisher auth tiktok --account A`.

IMPORTANT: until TikTok audits your app, every post is PRIVATE (SELF_ONLY), the posting
account must itself be private, and max 5 users per 24 h. Route TikTok through Ayrshare
(already audited) to post publicly before your audit passes.
"""

from __future__ import annotations

import secrets
import time
import urllib.parse
from pathlib import Path

from .base import PostRequest, PostResult, http, load_json, poll, save_json

API = "https://open.tiktokapis.com/v2"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.publish"
MIN_CHUNK, MAX_CHUNK = 5 * 1024 * 1024, 64 * 1024 * 1024


def auth_url(client_key: str, redirect_uri: str, state: str | None = None) -> tuple[str, str]:
    state = state or secrets.token_urlsafe(16)
    q = urllib.parse.urlencode({"client_key": client_key, "scope": SCOPES, "response_type": "code",
                                "redirect_uri": redirect_uri, "state": state})
    return f"{AUTH_URL}?{q}", state


def exchange_code(client_key: str, client_secret: str, redirect_url_or_code: str, redirect_uri: str,
                  token_path: str, *, opener=None) -> dict:
    """Accepts the full URL TikTok redirected to (or just the code) and saves tokens."""
    code = redirect_url_or_code
    if "://" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    kw = {"opener": opener} if opener else {}
    body = urllib.parse.urlencode({"client_key": client_key, "client_secret": client_secret, "code": code,
                                   "grant_type": "authorization_code", "redirect_uri": redirect_uri}).encode()
    _, _, res = http("POST", f"{API}/oauth/token/", data=body,
                     headers={"Content-Type": "application/x-www-form-urlencoded"}, **kw)
    if "access_token" not in res:
        raise RuntimeError(f"TikTok token exchange failed: {res}")
    tok = {"client_key": client_key, "client_secret": client_secret, **res,
           "expires_at": time.time() + int(res.get("expires_in", 86400))}
    save_json(token_path, tok)
    return {"token_path": token_path, "open_id": res.get("open_id"), "scope": res.get("scope")}


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) per TikTok rules: chunks 5-64 MB, last chunk absorbs the rest."""
    if size <= MAX_CHUNK:
        return size, 1
    chunk = MAX_CHUNK
    return chunk, size // chunk  # remainder is merged into the final chunk (allowed up to 128 MB)


class TikTokPublisher:
    def __init__(self, token_path: str, *, privacy: str = "PUBLIC_TO_EVERYONE", opener=None, sleep=time.sleep):
        self.token_path = token_path
        self.privacy = privacy
        self.kw = {"opener": opener} if opener else {}
        self.sleep = sleep

    def _token(self) -> str:
        tok = load_json(self.token_path)
        if not tok:
            raise RuntimeError(f"no TikTok token at {self.token_path}; run `auth tiktok` first")
        if tok.get("expires_at", 0) > time.time() + 60:
            return tok["access_token"]
        body = urllib.parse.urlencode({"client_key": tok["client_key"], "client_secret": tok["client_secret"],
                                       "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]}).encode()
        _, _, res = http("POST", f"{API}/oauth/token/", data=body,
                         headers={"Content-Type": "application/x-www-form-urlencoded"}, **self.kw)
        tok.update(res)
        tok["expires_at"] = time.time() + int(res.get("expires_in", 86400))
        save_json(self.token_path, tok)
        return tok["access_token"]

    def publish(self, req: PostRequest) -> PostResult:
        token = self._token()
        auth = {"Authorization": f"Bearer {token}"}
        _, _, info = http("POST", f"{API}/post/publish/creator_info/query/", json_body={}, headers=auth, **self.kw)
        options = ((info.get("data") or {}).get("privacy_level_options")) or ["SELF_ONLY"]
        privacy = self.privacy if self.privacy in options else options[0]
        size = Path(req.video_path).stat().st_size
        chunk, count = chunk_plan(size)
        _, _, init = http("POST", f"{API}/post/publish/video/init/", headers=auth, json_body={
            "post_info": {"title": req.caption[:2200], "privacy_level": privacy, "disable_duet": False,
                          "disable_comment": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                            "total_chunk_count": count},
        }, **self.kw)
        err = (init.get("error") or {})
        if err.get("code") not in (None, "ok"):
            raise RuntimeError(f"TikTok init failed: {err}")
        data = init["data"]
        upload_url, publish_id = data["upload_url"], data["publish_id"]
        blob = Path(req.video_path).read_bytes()
        for i in range(count):
            start = i * chunk
            end = size if i == count - 1 else start + chunk
            http("PUT", upload_url, data=blob[start:end], timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Range": f"bytes {start}-{end - 1}/{size}"}, **self.kw)

        def check():
            _, _, st = http("POST", f"{API}/post/publish/status/fetch/", headers=auth,
                            json_body={"publish_id": publish_id}, **self.kw)
            status = (st.get("data") or {}).get("status")
            if status == "FAILED":
                raise RuntimeError(f"TikTok processing failed: {st}")
            return status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"), st

        st = poll(check, every=3, timeout=300, sleep=self.sleep)
        ids = ((st.get("data") or {}).get("publicaly_available_post_id")
               or (st.get("data") or {}).get("publicly_available_post_id") or [])
        post_id = str(ids[0]) if ids else publish_id
        return PostResult("tiktok", True, post_id=post_id, visibility=privacy.lower(),
                          url=f"https://www.tiktok.com/video/{ids[0]}" if ids else None,
                          detail={"publish_id": publish_id, "privacy_options": options})
