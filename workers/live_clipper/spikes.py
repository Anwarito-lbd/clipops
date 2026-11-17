"""Chat-velocity spike detection: "it counts Twitch chat every 10 seconds".

Messages are bucketed into fixed windows (default 10 s). Each closed bucket is
compared against a rolling baseline of the buckets before it (median + MAD, with
a Poisson floor so a quiet chat doesn't trigger on 3 -> 9 messages). A bucket is
a spike when it is both a big multiple of the baseline and a statistical outlier.
A cooldown stops one moment from producing several overlapping clips.

Pure Python, no I/O — the same detector runs live and on a replayed chat log.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Iterable

HYPE_RE = re.compile(
    r"(?i)\b("
    r"let'?s\s*go+|lets+go+|w+|holy|omg+|lmao+|lmfao+|kekw|omegalul|lul+|pog\w*|"
    r"no\s*way+|clip\s*(it|that|this)|wtf+|insane|hype|bro+|what+|nah+|"
    r"he\s*did\s*not|she\s*did\s*not|o7|monka\w*"
    r")\b"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']{1,}")
STOPWORDS = frozenset(
    "THE A AN AND OR BUT IS ARE WAS WERE BE THIS THAT THESE IT ITS IT'S TO OF IN ON AT FOR WITH HE SHE THEY WE "
    "YOU I ME MY HIS HER SO JUST LIKE GET GOT DO DID NOT NO YES ALL WHAT HOW WHY OK".split()
)


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam). Used so low-volume chats don't fire on random noise."""
    if k <= 0:
        return 1.0
    lam = max(lam, 1e-9)
    if k <= lam:
        return 1.0  # never a spike; avoids summing the bulk of the distribution
    term = math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))
    total, i = 0.0, k
    while term > 0 and (total == 0.0 or term > total * 1e-12) and i < k + 100_000:
        total += term
        i += 1
        term *= lam / i
    return min(1.0, total)


@dataclass
class ChatMessage:
    ts: float  # wall-clock epoch seconds (live) or seconds from VOD start (replay)
    user: str
    text: str


@dataclass
class Bucket:
    index: int
    start: float
    end: float
    count: int = 0  # spam-capped message count
    raw_count: int = 0
    unique_users: int = 0
    hype: int = 0
    terms: Counter = field(default_factory=Counter)
    categories: Counter = field(default_factory=Counter)
    phrases: Counter = field(default_factory=Counter)
    _per_user: Counter = field(default_factory=Counter)


@dataclass
class Spike:
    bucket_start: float
    bucket_end: float
    count: int
    baseline: float
    ratio: float
    zscore: float
    p_value: float
    hype_ratio: float
    unique_users: int
    score: float
    top_terms: list[str]
    top_messages: list[str] = field(default_factory=list)  # chat's most-repeated full messages
    categories: dict = field(default_factory=dict)  # moment category -> chat hits in the bucket
    detected_at: float = 0.0  # stream/wall time the spike was confirmed
    early: bool = False  # fired mid-bucket, before the 10 s window closed

    def to_dict(self) -> dict:
        return asdict(self)


class ChatSpikeDetector:
    def __init__(
        self,
        *,
        bucket_seconds: float = 10.0,
        baseline_buckets: int = 18,
        warmup_buckets: int = 3,
        min_messages: int = 8,
        ratio_threshold: float = 2.5,
        z_threshold: float = 2.5,
        max_p_value: float = 1e-4,
        cooldown_seconds: float = 45.0,
        per_user_cap: int = 2,
        origin: float | None = None,
        extra_hype_terms: Iterable[str] = (),
        categories: dict[str, "re.Pattern"] | None = None,
    ) -> None:
        self.bucket_seconds = float(bucket_seconds)
        self.baseline_buckets = int(baseline_buckets)
        self.warmup_buckets = int(warmup_buckets)
        self.min_messages = int(min_messages)
        self.ratio_threshold = float(ratio_threshold)
        self.z_threshold = float(z_threshold)
        self.max_p_value = float(max_p_value)
        self.cooldown_seconds = float(cooldown_seconds)
        self.per_user_cap = int(per_user_cap)
        self.category_res = dict(categories or {})
        terms = [re.escape(t.strip()).replace(r"\ ", r"\s*") for t in extra_hype_terms if t.strip()]
        self._extra_re = re.compile(r"(?i)\b(" + "|".join(terms) + r")\b") if terms else None
        self.origin = origin
        self.closed: list[Bucket] = []
        self.spikes: list[Spike] = []
        self._open: dict[int, Bucket] = {}
        self._next_close = 0
        self._last_spike_end: float | None = None

    # -- bucketing ---------------------------------------------------------
    def _index(self, ts: float) -> int:
        if self.origin is None:
            self.origin = ts
        return int(math.floor((ts - self.origin) / self.bucket_seconds))

    def _bucket(self, idx: int) -> Bucket:
        b = self._open.get(idx)
        if b is None:
            start = (self.origin or 0.0) + idx * self.bucket_seconds
            b = Bucket(index=idx, start=start, end=start + self.bucket_seconds)
            self._open[idx] = b
        return b

    def add(self, msg: ChatMessage) -> list[Spike]:
        """Add one message; returns spikes from any buckets this message's time closed."""
        idx = self._index(msg.ts)
        out = self.tick(msg.ts)
        if idx < self._next_close:
            return out  # late message for an already-evaluated bucket
        b = self._bucket(idx)
        b.raw_count += 1
        b._per_user[msg.user] += 1
        if b._per_user[msg.user] <= self.per_user_cap:
            b.count += 1
            text = msg.text or ""
            if HYPE_RE.search(text) or (self._extra_re is not None and self._extra_re.search(text)):
                b.hype += 1
            for name, rx in self.category_res.items():
                if rx.search(text):
                    b.categories[name] += 1
            phrase = " ".join(text.upper().split())
            if 2 <= len(phrase) <= 40 and not phrase.startswith(("!", "@", "HTTP")):
                b.phrases[phrase] += 1
            for w in {w.upper() for w in _WORD_RE.findall(text)} - STOPWORDS:
                b.terms[w] += 1
        b.unique_users = len(b._per_user)
        # Early trigger: the thresholds are on raw counts, so a partial bucket that already
        # clears them is a confirmed spike — fire now instead of waiting for the bucket to close.
        if idx == self._next_close:
            early = self._evaluate(b, now=msg.ts, early=True)
            if early:
                self.spikes.append(early)
                out.append(early)
        return out

    def tick(self, now: float) -> list[Spike]:
        """Close every bucket that ended at or before `now` (call this even when chat is silent)."""
        if self.origin is None:
            return []
        current = int(math.floor((now - self.origin) / self.bucket_seconds))
        out: list[Spike] = []
        while self._next_close < current:
            b = self._open.pop(self._next_close, None) or self._bucket_empty(self._next_close)
            spike = self._evaluate(b, now=b.end)
            self.closed.append(b)
            if spike:
                self.spikes.append(spike)
                out.append(spike)
            self._next_close += 1
        return out

    def flush(self) -> list[Spike]:
        if self.origin is None:
            return []
        last = max(self._open) if self._open else self._next_close - 1
        return self.tick(self.origin + (last + 1) * self.bucket_seconds)

    def _bucket_empty(self, idx: int) -> Bucket:
        start = (self.origin or 0.0) + idx * self.bucket_seconds
        return Bucket(index=idx, start=start, end=start + self.bucket_seconds)

    # -- scoring -----------------------------------------------------------
    def _baseline(self) -> tuple[float, float] | None:
        hist = [b.count for b in self.closed[-self.baseline_buckets :]]
        if len(hist) < self.warmup_buckets:
            return None
        med = float(median(hist))
        mad = float(median([abs(c - med) for c in hist])) * 1.4826
        sigma = max(mad, math.sqrt(max(med, 1.0)), 1.0)  # Poisson floor
        return med, sigma

    def _evaluate(self, b: Bucket, *, now: float, early: bool = False) -> Spike | None:
        base = self._baseline()
        if base is None or b.count < self.min_messages:
            return None
        med, sigma = base
        ratio = b.count / max(med, 1.0)
        z = (b.count - med) / sigma
        if ratio < self.ratio_threshold or z < self.z_threshold:
            return None
        p_value = poisson_sf(b.count, max(med, 1.0))
        if p_value > self.max_p_value:
            return None
        if self._last_spike_end is not None and b.start < self._last_spike_end + self.cooldown_seconds:
            return None
        self._last_spike_end = b.end
        hype_ratio = b.hype / max(b.count, 1)
        score = round(z * (1.0 + hype_ratio) * min(1.0, b.unique_users / max(b.count, 1) + 0.25), 2)
        return Spike(
            bucket_start=b.start,
            bucket_end=b.end,
            count=b.count,
            baseline=round(med, 2),
            ratio=round(ratio, 2),
            zscore=round(z, 2),
            p_value=float(f"{p_value:.3g}"),
            hype_ratio=round(hype_ratio, 2),
            unique_users=b.unique_users,
            score=score,
            top_terms=[t for t, _ in b.terms.most_common(5)],
            top_messages=[t for t, n in b.phrases.most_common(5) if n >= 2],
            categories=dict(b.categories.most_common(4)),
            detected_at=round(now, 3),
            early=early,
        )

    def sustain(self, spike: Spike) -> dict:
        """How long chat stayed elevated after the spike — big moments keep chat going."""
        n, total, cats = 0, 0, Counter()
        for b in self.closed:
            if b.start < spike.bucket_start:
                continue
            if b.count >= max(2.0 * spike.baseline, self.min_messages / 2):
                n += 1
                total += b.count
                cats.update(b.categories)
            else:
                break
        if not cats:
            cats.update(spike.categories)
        final = bool(self.closed) and self.closed[-1].start > spike.bucket_start + n * self.bucket_seconds - 1e-6
        return {"buckets": n, "seconds": n * self.bucket_seconds, "messages": total, "final": final,
                "categories": dict(cats.most_common(4))}

    def bucket_series(self) -> list[dict]:
        """msgs / bucket series for charts (the bar graph in the Studio)."""
        return [
            {"start": b.start, "end": b.end, "count": b.count, "raw_count": b.raw_count, "hype": b.hype}
            for b in self.closed
        ]


def detect_spikes(messages: Iterable[ChatMessage], **kwargs) -> tuple[list[Spike], ChatSpikeDetector]:
    """Offline helper: run the detector over a finished chat log."""
    det = ChatSpikeDetector(**kwargs)
    for m in sorted(messages, key=lambda m: m.ts):
        det.add(m)
    det.flush()
    return det.spikes, det
