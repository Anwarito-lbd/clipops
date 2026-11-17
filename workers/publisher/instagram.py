"""Instagram Reels via the official Instagram Graph API (resumable upload to rupload.facebook.com).

Setup (once): Instagram Business/Creator account linked to a Facebook Page -> Meta app
(developers.facebook.com, use case "Manage messaging & content on Instagram") with
`instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`
-> your own accounts work in Development mode (add them as app testers/roles) ->
`python -m workers.publisher auth instagram --account A --short-token <token from Graph API Explorer>`.

Meta caps API publishing at 50 posts per rolling 24 h per account (GET /{ig-id}/content_publishing_limit).
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

from .base import PostRequest, PostResult, http, load_json, poll, save_json

GRAPH_VERSION = "v25.0"


def graph(version: str = GRAPH_VERSION) -> str:
    return f"https://graph.facebook.com/{version}"


def exchange_token(app_id: str, app_secret: str, short_token: str, token_path: str, *,
                   version: str = GRAPH_VERSION, opener=None) -> dict:
    """Short-lived user token -> long-lived (~60 day) token; finds the linked IG business account."""
    kw = {"opener": opener} if opener else {}
    q = urllib.parse.urlencode({"grant_type": "fb_exchange_token", "client_id": app_id,
                                "client_secret": app_secret, "fb_exchange_token": short_token})
    _, _, res = http("GET", f"{graph(version)}/oauth/access_token?{q}", **kw)
    long_token = res["access_token"]
    q = urllib.parse.urlencode({"fields": "name,instagram_business_account{id,username}", "access_token": long_token})
    _, _, pages = http("GET", f"{graph(version)}/me/accounts?{q}", **kw)
    igs = [p["instagram_business_account"] for p in pages.get("data", []) if p.get("instagram_business_account")]
    if not igs:
        raise RuntimeError("no Instagram Business/Creator account linked to your Facebook Pages")
    tok = {"access_token": long_token, "ig_user_id": igs[0]["id"], "username": igs[0].get("username"),
           "app_id": app_id, "version": version, "expires_at": time.time() + int(res.get("expires_in", 5184000)),
           "all_accounts": igs}
    save_json(token_path, tok)
    return {"token_path": token_path, "ig_user_id": tok["ig_user_id"], "username": tok["username"]}


class InstagramPublisher:
    def __init__(self, token_path: str, *, share_to_feed: bool = True, opener=None, sleep=time.sleep):
        self.token_path = token_path
        self.share_to_feed = share_to_feed
        self.kw = {"opener": opener} if opener else {}
        self.sleep = sleep

    def publish(self, req: PostRequest) -> PostResult:
        tok = load_json(self.token_path)
        if not tok:
            raise RuntimeError(f"no Instagram token at {self.token_path}; run `auth instagram` first")
        if tok.get("expires_at", 0) < time.time():
            raise RuntimeError("Instagram long-lived token expired; run `auth instagram` again")
        token, ig, base = tok["access_token"], tok["ig_user_id"], graph(tok.get("version", GRAPH_VERSION))
        q = urllib.parse.urlencode({"media_type": "REELS", "upload_type": "resumable", "caption": req.caption[:2200],
                                    "share_to_feed": str(self.share_to_feed).lower(), "access_token": token})
        _, _, container = http("POST", f"{base}/{ig}/media?{q}", **self.kw)
        cid, uri = container["id"], container.get("uri")
        if not uri:
            raise RuntimeError(f"Instagram did not return an upload uri: {container}")
        blob = Path(req.video_path).read_bytes()
        http("POST", uri, data=blob, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(blob))}, **self.kw)

        def check():
            q2 = urllib.parse.urlencode({"fields": "status_code,status", "access_token": token})
            _, _, st = http("GET", f"{base}/{cid}?{q2}", **self.kw)
            code = st.get("status_code")
            if code in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram processing {code}: {st.get('status')}")
            return code in ("FINISHED", "PUBLISHED"), st

        poll(check, every=4, timeout=600, sleep=self.sleep)
        q3 = urllib.parse.urlencode({"creation_id": cid, "access_token": token})
        _, _, pub = http("POST", f"{base}/{ig}/media_publish?{q3}", **self.kw)
        media_id = pub.get("id")
        permalink = None
        try:
            q4 = urllib.parse.urlencode({"fields": "permalink", "access_token": token})
            _, _, m = http("GET", f"{base}/{media_id}?{q4}", **self.kw)
            permalink = m.get("permalink")
        except Exception:  # permalink is a nice-to-have
            pass
        return PostResult("instagram", bool(media_id), post_id=media_id, url=permalink, visibility="public",
                          detail={"container_id": cid, "username": tok.get("username")})
