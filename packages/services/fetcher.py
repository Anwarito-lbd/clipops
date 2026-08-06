"""Download campaign footage from the links the Brief button collected.

Two very different jobs sit behind one entry point:

  - Streaming sources (Twitch VODs, YouTube) need yt-dlp, which knows how to
    resolve manifests and merge separate audio/video streams.
  - Direct media links are a plain HTTPS GET.

Neither can touch footage behind a login. A Google Drive folder shared only with
the operator's account is unreachable from a server that has no browser session,
and the failure mode matters: without a check, the "download" succeeds and saves
Google's sign-in page as an .mp4. Those cases must fail loudly and tell the
operator to fetch the file themselves into the drop folder.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

from app.storage_security import ALLOWED_VIDEO_EXTENSIONS, sanitize_filename

# Hosts that need a real browser session for anything non-public.
_LOGIN_WALLED = ("drive.google.com", "docs.google.com", "onedrive.live.com", "1drv.ms")

# Sources where yt-dlp does the heavy lifting.
_STREAMING = (
    "twitch.tv", "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
    "streamable.com", "facebook.com", "instagram.com", "tiktok.com", "x.com",
    "twitter.com", "reddit.com", "kick.com",
)

_HTML_SNIFF = (b"<!doctype html", b"<html", b"<!DOCTYPE HTML")


@dataclass
class FetchResult:
    url: str
    ok: bool
    path: str | None = None
    bytes_written: int = 0
    kind: str = "unknown"
    error: str | None = None
    manual_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnsafeURL(ValueError):
    """The URL resolves somewhere a server-side fetch must not go."""


def assert_public_https(url: str) -> str:
    """Reject anything but https to a public address.

    Without this, a campaign link could point at 169.254.169.254 or a machine on
    the operator's own network and the API would fetch it on request.
    """
    parts = urlparse(url)
    if parts.scheme != "https":
        raise UnsafeURL(f"Only https is allowed, got {parts.scheme or '(none)'}")
    host = parts.hostname
    if not host:
        raise UnsafeURL("URL has no host")

    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"Cannot resolve {host}: {exc}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURL(f"{host} resolves to a non-public address ({ip})")
    return host


def classify(url: str) -> str:
    """direct_media | streaming | login_walled | unknown."""
    host = (urlparse(url).hostname or "").lower()
    path = (urlparse(url).path or "").lower()
    if any(h in host for h in _STREAMING):
        return "streaming"
    if Path(path).suffix in ALLOWED_VIDEO_EXTENSIONS:
        return "direct_media"
    if any(h in host for h in _LOGIN_WALLED):
        return "login_walled"
    return "unknown"


def drive_direct_url(url: str) -> str | None:
    """Rewrite a Drive share link to its download endpoint, when public."""
    parts = urlparse(url)
    if "drive.google.com" not in (parts.hostname or ""):
        return None
    file_id = None
    seg = [s for s in parts.path.split("/") if s]
    if "d" in seg:
        i = seg.index("d")
        if i + 1 < len(seg):
            file_id = seg[i + 1]
    if not file_id:
        file_id = (parse_qs(parts.query).get("id") or [None])[0]
    if not file_id:
        # A folder link has no single file to fetch.
        return None
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _stream_to_disk(resp, dest: Path, max_bytes: int) -> int:
    """Write a response body, aborting the moment it exceeds the cap."""
    written = 0
    first = b""
    with dest.open("wb") as fh:
        for chunk in resp.iter_bytes(65536):
            if not first:
                first = chunk[:64]
                # A login page returned with 200 is the usual gated-link failure.
                if any(first.lstrip().lower().startswith(m.lower()) for m in _HTML_SNIFF):
                    raise ValueError(
                        "Server returned an HTML page, not a video - the link is "
                        "probably behind a login"
                    )
            written += len(chunk)
            if written > max_bytes:
                raise ValueError(
                    f"File exceeds the {max_bytes // (1024 * 1024)} MB limit"
                )
            fh.write(chunk)
    return written


def fetch_direct(url: str, dest_dir: Path, max_bytes: int, timeout: float = 60.0) -> FetchResult:
    """Download a direct media URL over HTTPS."""
    import httpx

    try:
        assert_public_https(url)
    except UnsafeURL as exc:
        return FetchResult(url, False, kind="direct_media", error=str(exc))

    name = sanitize_filename(Path(urlparse(url).path).name or "download.mp4")
    if Path(name).suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        name += ".mp4"
    dest = dest_dir / name
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, max_redirects=5) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return FetchResult(
                        url, False, kind="direct_media",
                        error=f"HTTP {resp.status_code}",
                    )
                ctype = (resp.headers.get("content-type") or "").lower()
                if ctype and not (
                    ctype.startswith("video/")
                    or ctype.startswith("application/octet-stream")
                ):
                    return FetchResult(
                        url, False, kind="direct_media",
                        error=f"Not a video (content-type: {ctype})",
                        manual_reason="The link did not serve a video file.",
                    )
                written = _stream_to_disk(resp, dest, max_bytes)
        return FetchResult(url, True, str(dest), written, "direct_media")
    except Exception as exc:  # noqa: BLE001 - report, never crash the request
        dest.unlink(missing_ok=True)
        msg = str(exc)
        return FetchResult(
            url, False, kind="direct_media", error=msg,
            manual_reason=(
                "Download this one yourself and drop it in the inbox."
                if "login" in msg.lower() else None
            ),
        )


def fetch_streaming(url: str, dest_dir: Path, max_bytes: int) -> FetchResult:
    """Download a VOD via yt-dlp, capped to 1080p to keep files sane."""
    try:
        import yt_dlp
    except ImportError:
        return FetchResult(url, False, kind="streaming", error="yt-dlp is not installed")

    try:
        assert_public_https(url)
    except UnsafeURL as exc:
        return FetchResult(url, False, kind="streaming", error=str(exc))

    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(dest_dir / "%(title).80s-%(id)s.%(ext)s"),
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": max_bytes,
        "retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
            if path.suffix != ".mp4":
                merged = path.with_suffix(".mp4")
                if merged.exists():
                    path = merged
            if not path.exists() or path.stat().st_size == 0:
                return FetchResult(
                    url, False, kind="streaming",
                    error="yt-dlp produced no file (likely over the size cap)",
                )
            return FetchResult(url, True, str(path), path.stat().st_size, "streaming")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        private = any(
            w in msg.lower() for w in ("private", "login", "sign in", "members-only", "age")
        )
        return FetchResult(
            url, False, kind="streaming", error=msg[:300],
            manual_reason=(
                "This video needs an account. Download it in your browser and "
                "drop it in the inbox."
                if private else None
            ),
        )


def fetch(url: str, dest_dir: Path, max_bytes: int) -> FetchResult:
    """Fetch one campaign resource, choosing the right strategy."""
    kind = classify(url)

    if kind == "login_walled":
        direct = drive_direct_url(url)
        if direct is None:
            return FetchResult(
                url, False, kind=kind,
                error="Shared folder or non-file link",
                manual_reason=(
                    "Folder links and private files cannot be fetched by the "
                    "server - open it, download the video, and drop it in the inbox."
                ),
            )
        return fetch_direct(direct, dest_dir, max_bytes)

    if kind == "streaming":
        return fetch_streaming(url, dest_dir, max_bytes)

    if kind == "direct_media":
        return fetch_direct(url, dest_dir, max_bytes)

    # Unknown shape: try yt-dlp, which recognises far more hosts than the list above.
    result = fetch_streaming(url, dest_dir, max_bytes)
    if not result.ok:
        result.manual_reason = result.manual_reason or (
            "Could not identify this link as a video. Download it manually if it is one."
        )
    return result
