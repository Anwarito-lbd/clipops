"""Original drift-phonk generator (royalty-free: everything is synthesised here).

Arrangement:  build (filtered cowbell + reverse swell + riser) -> tape-stop -> DROP:
  distorted 808 cowbell lead on a 3-3-2 tresillo rhythm in phrygian minor, with dotted-8th
  ping-pong delay and reverb; gliding, saturated 808 bass; half-time snare on beat 3;
  16th hats with 32nd rolls; kick-sidechained pump; master saturation + limiter. Stereo.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
PHRYGIAN = [0, 1, 3, 5, 7, 8, 10]
TRESILLO = [0, 3, 6, 8, 11, 14]  # 16th-step positions of the cowbell hits in a bar (3-3-2 feel)


def _env(n: int, decay: float, attack: float = 0.0015) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1.0, t / attack) * np.exp(-t / decay)


def _place(buf: np.ndarray, sig: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(round(t * SR))
    if i < 0 or i >= buf.shape[0]:
        return
    j = min(buf.shape[0], i + sig.shape[0])
    buf[i:j] += sig[: j - i] * gain


def _onepole(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    a = 1 - np.exp(-2 * np.pi * cutoff_hz / SR)
    # vectorised one-pole low-pass via scipy-free recursion in chunks
    y = np.empty_like(x)
    acc = 0.0
    for i in range(0, len(x), 4096):
        seg = x[i:i + 4096]
        out = np.empty_like(seg)
        for k, v in enumerate(seg):
            acc += a * (v - acc)
            out[k] = acc
        y[i:i + 4096] = out
    return y


def _conv(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]


def _reverb_ir(rng: np.random.Generator, seconds: float = 1.1) -> np.ndarray:
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.28 * SR))
    ir[: int(0.012 * SR)] = 0  # pre-delay
    return ir / np.abs(ir).sum() * 18


def _kick() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 160 * np.exp(-t * 35)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.16)
    click = np.random.default_rng(0).standard_normal(n) * _env(n, 0.004) * 0.25
    return np.tanh(2.2 * (body + click))


def _snare(rng: np.random.Generator) -> np.ndarray:
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 190 * t) * _env(n, 0.05)
    noise = np.diff(np.concatenate([[0.0], rng.standard_normal(n)])) * _env(n, 0.09)
    clap = sum(np.roll(noise * _env(n, 0.012), int(d * SR)) for d in (0, 0.011, 0.023)) * 0.5
    return np.tanh(1.8 * (0.5 * tone + 0.7 * noise + clap))


def _hat(rng: np.random.Generator, open_: bool = False) -> np.ndarray:
    n = int((0.22 if open_ else 0.045) * SR)
    x = np.diff(np.diff(rng.standard_normal(n + 2)))
    return x * _env(n, 0.07 if open_ else 0.011) * 0.22


def _cowbell(freq: float, dur: float = 0.26) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    sq = lambda f: np.sign(np.sin(2 * np.pi * f * t))  # noqa: E731
    tone = (sq(freq) + sq(freq * 1.4836) + 0.6 * sq(freq * 1.006) + 0.6 * sq(freq * 1.4836 * 0.994)) / 3.2
    body = np.tanh(2.5 * tone) * (0.7 * _env(n, 0.035) + 0.3 * _env(n, 0.12))
    return body


def _808(freqs: list[tuple[float, float]], total: float) -> np.ndarray:
    """Gliding 808: list of (start_time, freq) inside one note; returns `total` seconds."""
    n = int(total * SR)
    t = np.arange(n) / SR
    f = np.full(n, freqs[0][1])
    for (t0, f0), (t1, f1) in zip(freqs, freqs[1:]):
        i0, i1 = int(t0 * SR), int(t1 * SR)
        g = int(0.06 * SR)  # 60 ms glide
        f[i1:] = f1
        if i1 - g > i0:
            f[i1 - g:i1] = np.linspace(f0, f1, g)
    f *= 1 + 0.5 * np.exp(-t * 25)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (total * 0.9))
    return np.tanh(4.0 * s) * 0.75


def generate(
    out_wav: str | Path,
    *,
    bpm: float = 128.0,
    root_hz: float = 46.25,  # F#1
    build_beats: int = 12,
    drop_beats: int = 32,
    seed: int = 1,
) -> dict:
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    step = beat / 4
    drop_at = build_beats * beat
    total = drop_at + drop_beats * beat + 2.0
    n = int(total * SR)
    lead = np.zeros(n)
    bass = np.zeros(n)
    drums = np.zeros(n)
    kicks = np.zeros(n)

    # melody: 2-bar phrase on the tresillo grid, phrygian, cowbell 4 octaves above the bass
    degrees = rng.choice([0, 1, 3, 4, 2, 0, 5, 1], size=len(TRESILLO) * 2)
    phrase = [PHRYGIAN[d % 7] + 12 * (d // 7) + (12 if k % 6 == 4 else 0) for k, d in enumerate(degrees)]
    bell = root_hz * 16

    def bell_hits(t_from: float, t_to: float):
        bar = 4 * beat
        k = 0
        t_bar = t_from
        while t_bar < t_to:
            for pos in TRESILLO:
                t = t_bar + pos * step
                if t < t_to:
                    yield t, phrase[k % len(phrase)]
                k += 1
            t_bar += bar

    # build: same melody, low-passed, plus reverse swell and white-noise riser
    for t, note in bell_hits(0, drop_at - beat):
        _place(lead, _cowbell(bell * 2 ** (note / 12)), t, 0.55)
    build_end = int((drop_at - beat) * SR)
    lead[:build_end] = _onepole(lead[:build_end], 900) * 2.4
    rn = build_end
    rise = np.linspace(0, 1, rn) ** 3
    drums[:rn] += np.diff(np.concatenate([[0.0], rng.standard_normal(rn)])) * rise * 0.10
    # tape-stop on the last build beat: replay the last beat of lead slowing to a halt
    seg = lead[build_end - int(beat * SR):build_end].copy()
    speed = np.linspace(1.0, 0.0, len(seg)) ** 0.7
    idx = np.clip(np.cumsum(speed).astype(int), 0, len(seg) - 1)
    lead[build_end:build_end + len(seg)] += seg[idx] * np.linspace(1, 0, len(seg))

    # drop
    kick, snare = _kick(), _snare(rng)
    for b in range(drop_beats):
        t0 = drop_at + b * beat
        pos = b % 4
        if pos == 0 or (pos == 1 and b % 8 == 5):
            _place(kicks, kick, t0)
        if pos == 1:
            _place(kicks, kick, t0 + beat * 0.75, 0.8)
        if pos == 2:
            _place(drums, snare, t0, 0.85)
        roll = (b % 8 == 7)
        for s in range(8 if roll else 4):
            _place(drums, _hat(rng), t0 + s * beat / (8 if roll else 4), 0.9 if s % 2 == 0 else 0.55)
        if pos == 3:
            _place(drums, _hat(rng, open_=True), t0 + beat / 2, 0.5)
    for t, note in bell_hits(drop_at, drop_at + drop_beats * beat):
        _place(lead, _cowbell(bell * 2 ** (note / 12)), t, 0.6)
    bass_notes = [0, 0, 1, 0, 3, 0, 1, 7]  # per half-bar
    for h in range(drop_beats // 2):
        t0 = drop_at + h * 2 * beat
        root = root_hz * 2 ** (bass_notes[h % 8] / 12)
        nxt = root_hz * 2 ** (bass_notes[(h + 1) % 8] / 12)
        _place(bass, _808([(0, root), (beat * 1.5, nxt)], beat * 2.1), t0, 0.9)
    _place(kicks, _kick(), drop_at, 1.3)  # impact
    crash = np.diff(np.concatenate([[0.0], rng.standard_normal(int(1.6 * SR))])) * _env(int(1.6 * SR), 0.5) * 0.35
    _place(drums, crash, drop_at)

    # effects: dotted-8th ping-pong delay + reverb on the lead
    d = int(beat * 0.75 * SR)
    left, right = lead.copy(), lead.copy()
    for k, g in enumerate((0.42, 0.28, 0.18), start=1):
        tgt = left if k % 2 == 0 else right
        tgt[d * k:] += lead[:-d * k] * g
    ir = _reverb_ir(rng)
    left += _conv(left, ir) * 0.35
    right += _conv(right, ir) * 0.35

    # sidechain pump from the kicks
    env = np.abs(kicks)
    env = np.maximum.accumulate(env[::-1])[::-1] * 0 + np.convolve(env, np.ones(int(0.12 * SR)) / (0.12 * SR) * 40, "same")
    duck = 1 - 0.55 * np.clip(env, 0, 1)
    mid = (bass * duck) + kicks + drums
    L = mid + left * duck * 0.8
    R = mid + right * duck * 0.8
    out = np.stack([L, R], axis=1)
    out = np.tanh(out * 1.6)
    out /= max(1e-9, np.abs(out).max()) / 0.93
    fade = int(1.5 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    pcm = (out * 32767).astype(np.int16)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return {"path": str(out_wav), "bpm": bpm, "drop": drop_at, "duration": total, "beat": beat}
