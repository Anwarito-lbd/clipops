"""Scout: find who is live in a game category right now, ranked by viewers (Twitch Helix API).

Needs a free Twitch developer app (https://dev.twitch.tv/console/apps):
    TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET   (app access token, client-credentials flow)
Only public stream metadata is read.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

HELIX = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GTA6_CATEGORY_NAMES = ("Grand Theft Auto VI", "GTA VI", "Grand Theft Auto 6")


def _http_json(url: str, *, headers: dict | None = None, data: bytes | None = None, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method="POST" if data is not None else "GET")
    with opener(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TwitchScout:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, *, opener=urllib.request.urlopen):
        self.client_id = client_id or os.environ.get("TWITCH_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("TWITCH_CLIENT_SECRET", "")
        if not (self.client_id and self.client_secret):
            raise RuntimeError("set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET (free app at dev.twitch.tv/console/apps)")
        self._opener = opener
        self._token: str | None = None

    def _headers(self) -> dict:
        if not self._token:
            body = urllib.parse.urlencode({
                "client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials",
            }).encode()
            self._token = _http_json(TOKEN_URL, data=body, opener=self._opener)["access_token"]
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict) -> dict:
        qs = urllib.parse.urlencode(params, doseq=True)
        return _http_json(f"{HELIX}/{path}?{qs}", headers=self._headers(), opener=self._opener)

    def game_id(self, names: tuple[str, ...] = GTA6_CATEGORY_NAMES) -> tuple[str, str]:
        data = self._get("games", {"name": list(names)}).get("data") or []
        if data:
            return data[0]["id"], data[0]["name"]
        found = self._get("search/categories", {"query": names[0], "first": 5}).get("data") or []
        if not found:
            raise LookupError(f"no Twitch category matching {names}")
        return found[0]["id"], found[0]["name"]

    def top_streams(self, *, names: tuple[str, ...] = GTA6_CATEGORY_NAMES, first: int = 20,
                    language: str | None = None) -> list[dict]:
        gid, gname = self.game_id(names)
        params: dict = {"game_id": gid, "first": min(100, max(1, first)), "type": "live"}
        if language:
            params["language"] = language
        rows = self._get("streams", params).get("data") or []
        rows.sort(key=lambda r: r.get("viewer_count", 0), reverse=True)
        return [
            {"channel": r["user_login"], "name": r.get("user_name"), "viewers": r.get("viewer_count", 0),
             "title": r.get("title", ""), "started_at": r.get("started_at"), "language": r.get("language"),
             "category": gname}
            for r in rows[:first]
        ]


def pick_channels(streams: list[dict], *, top: int, exclude: set[str] = frozenset(), min_viewers: int = 0) -> list[str]:
    out = []
    for s in streams:
        ch = s["channel"].lower()
        if ch in exclude or s["viewers"] < min_viewers:
            continue
        out.append(ch)
        if len(out) >= top:
            break
    return out
