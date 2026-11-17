"""YouTube Shorts upload via the official YouTube Data API v3 (resumable upload, stdlib HTTP).

Setup (once): Google Cloud project -> enable "YouTube Data API v3" -> OAuth client ID
(Desktop app) -> download client_secret.json -> `python -m workers.publisher auth youtube --account A`.

IMPORTANT: uploads from an *unaudited* API project are locked to PRIVATE by YouTube no matter
what privacyStatus you send. Apply via the "YouTube API Services - Audit and Quota Extension
Form" to post publicly, or route YouTube through Ayrshare (already audited) meanwhile.
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

from .base import PostRequest, PostResult, http, load_json, save_json

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
GAMING_CATEGORY = "20"


def authorize(client_secrets: str, token_path: str) -> dict:
    """Interactive browser consent (needs `pip install google-auth-oauthlib`). Saves a refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    data = {
        "client_id": creds.client_id, "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token, "access_token": creds.token,
        "expires_at": time.time() + 3000,
    }
    save_json(token_path, data)
    return {"token_path": token_path, "scopes": SCOPES}


class YouTubePublisher:
    def __init__(self, token_path: str, *, privacy: str = "public", audited: bool = False, opener=None):
        self.token_path = token_path
        self.privacy = privacy
        self.audited = audited
        self.kw = {"opener": opener} if opener else {}

    def _token(self) -> str:
        tok = load_json(self.token_path)
        if not tok or not tok.get("refresh_token"):
            raise RuntimeError(f"no YouTube token at {self.token_path}; run `auth youtube` first")
        if tok.get("access_token") and tok.get("expires_at", 0) > time.time() + 60:
            return tok["access_token"]
        body = urllib.parse.urlencode({
            "client_id": tok["client_id"], "client_secret": tok["client_secret"],
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token",
        }).encode()
        _, _, res = http("POST", TOKEN_URL, data=body,
                         headers={"Content-Type": "application/x-www-form-urlencoded"}, **self.kw)
        tok["access_token"] = res["access_token"]
        tok["expires_at"] = time.time() + int(res.get("expires_in", 3600))
        save_json(self.token_path, tok)
        return tok["access_token"]

    def publish(self, req: PostRequest) -> PostResult:
        token = self._token()
        size = Path(req.video_path).stat().st_size
        title = req.title.strip()[:100] or "GTA 6 moment"
        tags = [h.lstrip("#") for h in req.hashtags][:15]
        description = req.caption if "#shorts" in req.caption.lower() else f"{req.caption}\n#Shorts"
        meta = {
            "snippet": {"title": title, "description": description[:4900], "tags": tags,
                        "categoryId": GAMING_CATEGORY},
            "status": {"privacyStatus": self.privacy, "selfDeclaredMadeForKids": False},
        }
        _, headers, _ = http(
            "POST", f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status", json_body=meta,
            headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Length": str(size),
                     "X-Upload-Content-Type": "video/mp4"}, **self.kw,
        )
        session = headers.get("location")
        if not session:
            raise RuntimeError("YouTube did not return a resumable upload session")
        _, _, video = http("PUT", session, data=Path(req.video_path).read_bytes(),
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
                           timeout=600, **self.kw)
        vid = video.get("id")
        visibility = (video.get("status") or {}).get("privacyStatus", self.privacy)
        if not self.audited and self.privacy == "public":
            visibility = "private (unaudited API project)"
        return PostResult("youtube", bool(vid), post_id=vid, url=f"https://youtube.com/shorts/{vid}" if vid else None,
                          visibility=visibility, detail={"title": title})
