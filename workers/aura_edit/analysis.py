"""Music + footage analysis for aura edits.

Music: tempo, beat grid and the *drop* (biggest energy rise) via librosa.
Footage: scene cuts (PySceneDetect) scored for motion, colour and brightness with OpenCV,
so the build-up gets cinematic shots and the drop gets the most intense ones.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class MusicInfo:
    path: str
    duration: float
    tempo: float
    beats: list[float]
    drop: float

    @property
    def beat(self) -> float:
        return 60.0 / self.tempo if self.tempo else 0.5


def analyze_music(path: str, *, min_drop: float = 3.0) -> MusicInfo:
    import librosa  # type: ignore

    y, sr = librosa.load(path, sr=22050, mono=True)
    dur = len(y) / sr
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    beats = [float(b) for b in np.atleast_1d(beats)]
    # Fold half/double-time estimates into the 70-160 BPM range editors cut to.
    while tempo > 160:
        tempo /= 2
        beats = beats[::2]
    while 0 < tempo < 70:
        tempo *= 2
        beats = sorted(beats + [(a + b) / 2 for a, b in zip(beats, beats[1:])])
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    win = max(1, int(2.0 * sr / hop))
    best, drop = -1e9, min(dur / 3, 8.0)
    for i in range(win, len(rms) - win):
        if t[i] < min_drop or t[i] > dur - 6:
            continue
        rise = rms[i:i + win].mean() - rms[i - win:i].mean()
        if rise > best:
            best, drop = rise, float(t[i])
    if beats:  # snap the drop onto the beat grid
        drop = min(beats, key=lambda b: abs(b - drop))
    return MusicInfo(path=path, duration=dur, tempo=tempo, beats=beats, drop=drop)


@dataclass
class Shot:
    path: str
    start: float
    end: float
    motion: float
    color: float
    brightness: float
    kind: str = "video"  # video | image
    feat: list | None = None  # 8x4 Lab thumbnail of the middle frame (layout + colour), for matching
    hue: float = 0.0  # saturation-weighted mean hue, degrees (colour-flow ordering)
    sat: float = 0.0
    bars: tuple = (0.0, 0.0)  # letterbox (top, bottom) as fractions of height, cropped before reframing
    hq: tuple | None = None  # (path_or_url, time_offset): render from this higher-quality source instead
    sharp: float = 200.0  # Laplacian variance of a 320x180 sample: low = motion blur / soft focus

    @property
    def length(self) -> float:
        return self.end - self.start

    @property
    def is_card(self) -> bool:
        """Title / rating / date cards: dark, flat and nearly static."""
        return self.kind == "video" and self.color < 9 and self.motion < 8 and self.brightness < 60

    def score(self, want: str) -> float:
        if self.brightness < 25 or self.is_card:  # black / fade frames, text cards
            return -1.0
        crisp = min(1.0, self.sharp / 120.0)  # blurry shots never win the hero/hit slots
        if want == "hero":  # the drop / hook: bright, colourful, moving AND sharp
            return (self.color * 1.0 + min(self.motion, 30) * 0.8 + max(0.0, self.brightness - 50) * 0.5) * crisp ** 2
        if want == "intense":
            return (self.motion * 1.0 + self.color * 0.6 + max(0.0, self.brightness - 55) * 0.2) * (0.4 + 0.6 * crisp)
        return self.color * 1.0 + min(self.motion, 12) * 0.3  # cinematic: colourful, calmer


def _probe_duration(path: str) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path], text=True).strip()
    return float(out or 0)


def _scene_bounds(path: str, duration: float) -> list[tuple[float, float]]:
    try:
        from scenedetect import ContentDetector, detect  # type: ignore

        scenes = detect(path, ContentDetector(threshold=27.0, min_scene_len=8))
        bounds = [(s.get_seconds(), e.get_seconds()) for s, e in scenes]
    except Exception:
        bounds = []
    if not bounds:
        step = 2.0
        bounds = [(t, min(duration, t + step)) for t in np.arange(0, duration, step)]
    out = []
    for s, e in bounds:  # split long scenes so each window is a usable cut
        while e - s > 4.0:
            out.append((s, s + 3.0))
            s += 3.0
        if e - s >= 0.6:
            out.append((s, e))
    return out


def _frame_stats(cap, t: float):
    import cv2  # type: ignore

    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    if not ok:
        return None
    small = cv2.resize(frame, (160, 90))
    return small


def _features(frame) -> tuple[list, float, float]:
    import cv2  # type: ignore

    img = frame.astype(np.uint8)
    lab = cv2.cvtColor(cv2.resize(img, (8, 4), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32)
    hsv = cv2.cvtColor(cv2.resize(img, (40, 22)), cv2.COLOR_BGR2HSV).astype(np.float32)
    h = hsv[..., 0] * 2 * np.pi / 180  # OpenCV hue is 0-180
    w = hsv[..., 1] / 255 * (hsv[..., 2] / 255)
    hue = (np.degrees(np.arctan2((np.sin(h) * w).sum(), (np.cos(h) * w).sum())) + 360) % 360
    return (lab / 255).flatten().tolist(), float(hue), float(w.mean())


def letterbox(frames) -> tuple[float, float]:
    """Cinematic black bars baked into the frame: (top, bottom) fractions, from rows dark in every frame."""
    rows = np.max([f.astype(np.float32).mean(axis=(1, 2)) for f in frames], axis=0)
    h = len(rows)
    top = next((i for i in range(h // 3) if rows[i] > 14), h // 3)
    bot = next((i for i in range(h // 3) if rows[h - 1 - i] > 14), h // 3)
    if top < 0.03 * h:
        top = 0
    if bot < 0.03 * h:
        bot = 0
    return (round(top / h + 0.006, 4) if top else 0.0, round(bot / h + 0.006, 4) if bot else 0.0)


def add_letterbox(shots: list["Shot"]) -> None:
    """Fill `bars` for already-analysed shots (cheap: 3 frames each)."""
    import cv2  # type: ignore

    caps: dict = {}
    for s in shots:
        if s.kind == "image":
            continue
        cap = caps.setdefault(s.path, cv2.VideoCapture(s.path))
        frames = [x for x in (_frame_stats(cap, t) for t in np.linspace(s.start, s.end, 3)) if x is not None]
        if frames:
            s.bars = letterbox(frames)
    for c in caps.values():
        c.release()


def parse_source(spec: str) -> tuple[str, list[tuple[float, float]] | None]:
    """'file.mp4#2.8-76.6,80-85' -> (file.mp4, [(2.8, 76.6), (80, 85)]); no '#' = whole file."""
    if "#" not in spec:
        return spec, None
    path, ranges = spec.rsplit("#", 1)
    out = []
    for r in ranges.split(","):
        a, b = r.split("-")
        out.append((float(a), float(b)))
    return path, out


def analyze_footage(paths: list[str], *, trim_edges: float = 0.15) -> list[Shot]:
    """Each entry is a file path, optionally with '#start-end[,start-end]' ranges to keep."""
    import cv2  # type: ignore

    shots: list[Shot] = []
    for spec in paths:
        path, keep = parse_source(spec)
        if Path(path).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            img = cv2.imread(path)
            if img is None:
                continue
            small = cv2.resize(img, (160, 90)).astype(np.float32)
            feat, hue, sat = _features(small)
            shots.append(Shot(path, 0.0, 6.0, motion=6.0, color=_colorfulness(small),
                              brightness=float(small.mean()), kind="image", feat=feat, hue=hue, sat=sat))
            continue
        dur = _probe_duration(path)
        cap = cv2.VideoCapture(path)
        for s, e in _scene_bounds(path, dur):
            s2, e2 = s + trim_edges, e - trim_edges
            if keep:
                inside = [(max(s2, a), min(e2, b)) for a, b in keep if min(e2, b) - max(s2, a) > 0]
                if not inside:
                    continue
                s2, e2 = max(inside, key=lambda r: r[1] - r[0])
            if e2 - s2 < 0.5:
                continue
            samples = [x for x in (_frame_stats(cap, t) for t in np.linspace(s2, e2, 5)) if x is not None]
            if len(samples) < 2:
                continue
            arr = [x.astype(np.float32) for x in samples]
            motion = float(np.mean([np.abs(a - b).mean() for a, b in zip(arr, arr[1:])]))
            feat, hue, sat = _features(samples[len(samples) // 2])
            shots.append(Shot(path, s2, e2, motion=motion, color=float(np.mean([_colorfulness(a) for a in arr])),
                              brightness=float(np.mean([a.mean() for a in arr])), feat=feat, hue=hue, sat=sat,
                              bars=letterbox(samples)))
        cap.release()
    return shots


def _colorfulness(img) -> float:
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    rg, yb = np.abs(r - g), np.abs(0.5 * (r + g) - b)
    return float(math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def match_pairs(tops: list[Shot], bottoms: list[Shot], n: int) -> list[tuple[Shot, Shot, float]]:
    """Greedy best visual matches (layout + colour) between two pools, each shot used once."""
    a = [t for t in tops if t.feat and t.brightness >= 25]
    b = [x for x in bottoms if x.feat and x.brightness >= 25]
    if not a or not b:
        return []
    A, B = np.array([t.feat for t in a]), np.array([x.feat for x in b])
    d = ((A[:, None, :] - B[None, :, :]) ** 2).mean(axis=2)
    pairs, used_a, used_b = [], set(), set()
    for flat in np.argsort(d, axis=None):
        i, j = divmod(int(flat), d.shape[1])
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((a[i], b[j], float(d[i, j])))
        if len(pairs) >= n:
            break
    return pairs


def music_from_grid(path: str, bpm: float, drop: float, duration: float) -> MusicInfo:
    """Exact beat grid for music we generated ourselves (no detection error)."""
    beat = 60.0 / bpm
    beats = [round(k * beat, 4) for k in range(int(duration / beat) + 1)]
    return MusicInfo(path=path, duration=duration, tempo=bpm, beats=beats, drop=drop)


def add_sharpness(shots: list["Shot"]) -> None:
    """Laplacian-variance sharpness from the middle frame (320x180) of each shot."""
    import cv2  # type: ignore

    caps: dict = {}
    for s in shots:
        if s.kind == "image":
            img = cv2.imread(s.path, cv2.IMREAD_GRAYSCALE)
        else:
            cap = caps.setdefault(s.path, cv2.VideoCapture(s.path))
            cap.set(cv2.CAP_PROP_POS_MSEC, (s.start + s.end) / 2 * 1000)
            ok, frame = cap.read()
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if ok else None
        if img is not None:
            s.sharp = float(cv2.Laplacian(cv2.resize(img, (320, 180)), cv2.CV_64F).var())
    for c in caps.values():
        c.release()
