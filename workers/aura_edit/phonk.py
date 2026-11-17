"""Original phonk beat generator (royalty-free: everything is synthesised here).

Build-up: filtered cowbell melody + riser, then a short gap, then the DROP:
distorted 808s, kick, clap, 16th hats and the full cowbell. Deterministic per seed.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
MINOR = [0, 2, 3, 5, 7, 8, 10]


def _env(n: int, decay: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (decay * SR))


def _place(buf: np.ndarray, sig: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(t * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def _kick() -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 42 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.12)


def _808(freq: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = freq * (1 + 0.6 * np.exp(-t * 30))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, dur * 0.7)
    return np.tanh(3.2 * s) * 0.8


def _cowbell(freq: float, dur: float = 0.18) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    sq = np.sign(np.sin(2 * np.pi * freq * t)) + np.sign(np.sin(2 * np.pi * freq * 1.48 * t))
    return 0.5 * sq * _env(n, 0.05)


def _hat(rng: np.random.Generator, dur: float = 0.05) -> np.ndarray:
    n = int(dur * SR)
    x = np.diff(rng.standard_normal(n + 1))
    return x * _env(n, 0.012) * 0.35


def _clap(rng: np.random.Generator) -> np.ndarray:
    n = int(0.22 * SR)
    x = rng.standard_normal(n)
    x = np.diff(np.concatenate([[0], x])) * 0.6 + x * 0.4
    return x * _env(n, 0.06) * 0.6


def _lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # one-pole, only used on the short build-up
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def generate(
    out_wav: str | Path,
    *,
    bpm: float = 128.0,
    root_hz: float = 49.0,  # ~G1
    build_beats: int = 12,
    drop_beats: int = 28,
    seed: int = 1,
) -> dict:
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    drop_at = build_beats * beat
    total = drop_at + drop_beats * beat + 1.5
    buf = np.zeros(int(total * SR))
    deg = MINOR
    motif = [deg[i % 7] + 12 * (i // 7) for i in rng.choice([0, 2, 3, 4, 6, 7, 9], size=8)]
    bell_root = root_hz * 16  # cowbell sits 4 octaves up

    # build-up: filtered cowbell 8ths + noise riser, 1-beat silence gap before the drop
    build = np.zeros(int(drop_at * SR) + SR)
    for k in range(int((build_beats - 1) * 2)):
        note = motif[k % 8]
        _place(build, _cowbell(bell_root * 2 ** (note / 12)), k * beat / 2, 0.5)
    build = _lowpass(build, 0.08) * 2.2
    riser_n = int((build_beats - 1) * beat * SR)
    rt = np.linspace(0, 1, riser_n)
    riser = np.diff(rng.standard_normal(riser_n + 1)) * rt ** 2 * 0.12
    build[:riser_n] += riser
    gap = int((drop_at - beat * 0.5) * SR)
    build[gap:] = 0
    buf[: len(build[: int(drop_at * SR)])] += build[: int(drop_at * SR)]

    # drop: 2-bar pattern
    kick, clap = _kick(), _clap(rng)
    bass_line = [0, 0, 7, 5, 0, 0, 3, 10]
    for b in range(drop_beats):
        t0 = drop_at + b * beat
        bar_pos = b % 4
        if bar_pos in (0, 2) or (bar_pos == 3 and b % 8 == 7):
            _place(buf, kick, t0, 0.9)
        if bar_pos in (1, 3):
            _place(buf, clap, t0, 0.7)
        if b % 2 == 0:
            note = bass_line[(b // 2) % 8]
            _place(buf, _808(root_hz * 2 ** (note / 12), beat * 1.9), t0, 0.85)
        for s in range(4):
            _place(buf, _hat(rng), t0 + s * beat / 4, 0.9 if s % 2 == 0 else 0.5)
        for e in range(2):
            note = motif[(b * 2 + e) % 8]
            _place(buf, _cowbell(bell_root * 2 ** (note / 12)), t0 + e * beat / 2, 0.42)
    # big impact on the drop
    _place(buf, _kick(), drop_at, 1.2)
    _place(buf, _808(root_hz, beat * 3), drop_at, 1.0)

    buf = np.tanh(buf * 1.4)
    buf /= max(1e-9, np.abs(buf).max()) / 0.89
    fade = int(1.2 * SR)
    buf[-fade:] *= np.linspace(1, 0, fade)
    pcm = (buf * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    return {"path": str(out_wav), "bpm": bpm, "drop": drop_at, "duration": total, "beat": beat}
