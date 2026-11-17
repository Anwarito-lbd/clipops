"""Shared publishing types + a tiny HTTP layer (stdlib only, injectable for tests)."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

PLATFORMS = ("youtube", "tiktok", "instagram")


@dataclass
class PostRequest:
    clip_id: str
    video_path: str
    title: str  # YouTube title / first line elsewhere
    caption: str  # full caption incl. hashtags
    hashtags: list[str] = field(default_factory=list)
    account: str = ""
    cover_path: str | None = None
    streamer: str = ""


@dataclass
class PostResult:
    platform: str
    ok: bool
    post_id: str | None = None
    url: str | None = None
    visibility: str | None = None  # public | private | ...
    via: str = "official"
    error: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url.split('?')[0]}: {body[:500]}")
        self.status, self.body, self.url = status, body, url


Opener = Callable[..., Any]


def http(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json_body: Any = None,
    data: bytes | None = None,
    opener: Opener = urllib.request.urlopen,
    timeout: float = 120,
) -> tuple[int, dict, Any]:
    """Return (status, headers, parsed-json-or-text). Raises HttpError on 4xx/5xx."""
    hdrs = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json; charset=UTF-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
            resp_headers = {k.lower(): v for k, v in dict(getattr(resp, "headers", {}) or {}).items()}
    except urllib.error.HTTPError as exc:
        raise HttpError(exc.code, exc.read().decode("utf-8", "replace"), url) from exc
    text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
    try:
        body = json.loads(text) if text else {}
    except json.JSONDecodeError:
        body = text
    if status >= 400:
        raise HttpError(status, text, url)
    return status, resp_headers, body


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


def poll(fn: Callable[[], tuple[bool, Any]], *, every: float = 3.0, timeout: float = 300.0, sleep=time.sleep):
    """Call fn until it returns (True, value); raise TimeoutError after `timeout`."""
    deadline = time.monotonic() + timeout
    while True:
        done, value = fn()
        if done:
            return value
        if time.monotonic() > deadline:
            raise TimeoutError(f"gave up after {timeout:.0f}s: last state {value}")
        sleep(every)
