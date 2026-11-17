"""Read-only Twitch chat over anonymous IRC (no account, no token, never sends messages).

Twitch allows anonymous read-only IRC logins with a `justinfanNNNN` nick. We
request the `twitch.tv/tags` capability so each message carries `tmi-sent-ts`
(server time in ms), which keeps bucket timing accurate even if we fall behind.
"""

from __future__ import annotations

import json
import random
import socket
import ssl
import threading
import time
from pathlib import Path
from typing import Iterable, Iterator

from .spikes import ChatMessage

TWITCH_IRC_HOST = "irc.chat.twitch.tv"


def parse_irc_line(line: str, *, now: float | None = None) -> ChatMessage | None:
    """Parse one raw IRC line into a ChatMessage, or None if it isn't a PRIVMSG."""
    line = line.rstrip("\r\n")
    tags: dict[str, str] = {}
    if line.startswith("@"):
        raw_tags, _, line = line[1:].partition(" ")
        for kv in raw_tags.split(";"):
            k, _, v = kv.partition("=")
            tags[k] = v
    if " PRIVMSG " not in line:
        return None
    prefix, _, rest = line.partition(" PRIVMSG ")
    _channel, _, text = rest.partition(" :")
    user = tags.get("display-name") or prefix.lstrip(":").split("!", 1)[0]
    ts = now if now is not None else time.time()
    if tags.get("tmi-sent-ts", "").isdigit():
        ts = int(tags["tmi-sent-ts"]) / 1000.0
    return ChatMessage(ts=ts, user=user.lower(), text=text)


class TwitchChatReader:
    """Iterate chat messages from a live Twitch channel; reconnects with backoff."""

    def __init__(self, channel: str, *, host: str = TWITCH_IRC_HOST, port: int = 6697, use_ssl: bool = True):
        self.channel = channel.lower().lstrip("#")
        self.host, self.port, self.use_ssl = host, port, use_ssl
        self.connected = False

    def _connect(self) -> socket.socket:
        raw = socket.create_connection((self.host, self.port), timeout=30)
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host) if self.use_ssl else raw
        sock.settimeout(1.0)
        nick = f"justinfan{random.randint(10000, 99999)}"
        for cmd in ("CAP REQ :twitch.tv/tags", "PASS SCHMOOPIIE", f"NICK {nick}", f"JOIN #{self.channel}"):
            sock.sendall((cmd + "\r\n").encode())
        return sock

    def messages(self, stop: threading.Event) -> Iterator[ChatMessage]:
        backoff = 1.0
        while not stop.is_set():
            try:
                sock = self._connect()
                self.connected, backoff, buf = True, 1.0, b""
                while not stop.is_set():
                    try:
                        data = sock.recv(65536)
                    except (socket.timeout, TimeoutError):
                        continue
                    if not data:
                        raise ConnectionError("chat socket closed")
                    buf += data
                    *lines, buf = buf.split(b"\r\n")
                    for raw in lines:
                        line = raw.decode("utf-8", "replace")
                        if line.startswith("PING"):
                            sock.sendall(line.replace("PING", "PONG", 1).encode() + b"\r\n")
                            continue
                        msg = parse_irc_line(line)
                        if msg:
                            yield msg
                sock.close()
            except OSError:
                self.connected = False
                stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)


def write_chat_jsonl(path: str | Path, messages: Iterable[ChatMessage]) -> None:
    with Path(path).open("a", encoding="utf-8") as fh:
        for m in messages:
            fh.write(json.dumps({"ts": m.ts, "user": m.user, "text": m.text}) + "\n")


def load_chat_jsonl(path: str | Path, *, time_offset: float = 0.0) -> list[ChatMessage]:
    """Load a chat log. `time_offset` is subtracted from every ts (e.g. the VOD's start epoch)."""
    out: list[ChatMessage] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(ChatMessage(ts=float(d["ts"]) - time_offset, user=str(d.get("user", "")), text=str(d.get("text", ""))))
    return out


def replay_chat_realtime(
    messages: list[ChatMessage], stop: threading.Event, *, start_wall: float | None = None
) -> Iterator[ChatMessage]:
    """Re-emit a chat log (ts relative to 0) in real time, re-stamped to wall clock. For simulations."""
    start_wall = start_wall or time.time()
    for m in sorted(messages, key=lambda m: m.ts):
        delay = start_wall + m.ts - time.time()
        if delay > 0 and stop.wait(delay):
            return
        yield ChatMessage(ts=start_wall + m.ts, user=m.user, text=m.text)
