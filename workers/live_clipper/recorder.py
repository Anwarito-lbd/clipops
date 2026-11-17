"""Record a live stream into rolling 10 s MPEG-TS segments while it's still live.

    streamlink --stdout twitch.tv/<channel> best | ffmpeg -i pipe:0 -c copy -f segment ...

Each finished segment is listed (with its start/end time) in `segments.csv`, so
the cutter can grab any 30 s window as soon as it has been written — no need to
wait for the stream to end or download the VOD.

`source_file` mode replays a local video at 1x speed (`ffmpeg -re`) to simulate a
live stream for testing.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    path: Path
    start: float  # seconds from recording t=0
    end: float


class SegmentRecorder:
    def __init__(
        self,
        out_dir: str | Path,
        *,
        stream_url: str | None = None,
        source_file: str | None = None,
        quality: str = "best",
        segment_seconds: float = 10.0,
        retain_seconds: float | None = None,
        ffmpeg: str = "ffmpeg",
        streamlink: str = "streamlink",
    ) -> None:
        if not (stream_url or source_file):
            raise ValueError("stream_url or source_file is required")
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stream_url, self.source_file, self.quality = stream_url, source_file, quality
        self.segment_seconds = segment_seconds
        self.retain_seconds = retain_seconds
        self.ffmpeg, self.streamlink = ffmpeg, streamlink
        self.list_path = self.dir / "segments.csv"
        self.started_at: float | None = None  # wall clock of recording t=0
        self._procs: list[subprocess.Popen] = []
        self._watch: threading.Thread | None = None
        self._stop = threading.Event()

    # -- commands ----------------------------------------------------------
    def build_commands(self) -> tuple[list[str] | None, list[str]]:
        seg_out = [
            "-f", "segment",
            "-segment_time", str(self.segment_seconds),
            "-segment_format", "mpegts",
            "-segment_list", str(self.list_path),
            "-segment_list_type", "csv",
            "-segment_list_size", "0",
            str(self.dir / "seg_%06d.ts"),
        ]
        if self.source_file:
            # Simulated live: real-time read, re-encode so keyframes land every 2 s.
            ff = [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-re", "-i", self.source_file,
                "-c:v", "libx264", "-preset", "veryfast", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
                "-c:a", "aac", "-b:a", "128k", *seg_out,
            ]
            return None, ff
        sl = [
            self.streamlink, "--stdout", "--twitch-disable-ads", "--twitch-low-latency",
            "--hls-live-edge", "2", "--retry-streams", "5", "--retry-open", "3",
            self.stream_url, self.quality,
        ]
        ff = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", "pipe:0", "-c", "copy", *seg_out]
        return sl, ff

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self.stream_url and not shutil.which(self.streamlink):
            raise RuntimeError("streamlink not found — `pip install streamlink`")
        sl_cmd, ff_cmd = self.build_commands()
        if sl_cmd:
            sl = subprocess.Popen(sl_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            ff = subprocess.Popen(ff_cmd, stdin=sl.stdout, stderr=subprocess.PIPE)
            assert sl.stdout is not None
            sl.stdout.close()  # let ffmpeg own the pipe
            self._procs = [sl, ff]
        else:
            self._procs = [subprocess.Popen(ff_cmd, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE)]
        self._watch = threading.Thread(target=self._watch_first_segment, daemon=True)
        self._watch.start()

    def _watch_first_segment(self) -> None:
        # t=0 of the recording ≈ the moment ffmpeg creates the first segment file.
        first = self.dir / "seg_000000.ts"
        while not self._stop.is_set() and self.started_at is None:
            if first.exists():
                self.started_at = time.time()
                break
            if not self.alive():
                break
            time.sleep(0.05)
        while not self._stop.wait(self.segment_seconds):
            self._prune()

    def alive(self) -> bool:
        return bool(self._procs) and self._procs[-1].poll() is None

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        for p in self._procs:
            if p.poll() is None:
                p.terminate()
        for p in self._procs:
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()

    def wait(self) -> None:
        for p in self._procs:
            p.wait()

    def error_output(self) -> str:
        ff = self._procs[-1] if self._procs else None
        if ff and ff.poll() is not None and ff.stderr:
            return ff.stderr.read().decode("utf-8", "replace")[-2000:]
        return ""

    # -- segment index -----------------------------------------------------
    def segments(self) -> list[Segment]:
        return read_segment_list(self.list_path)

    def recorded_until(self) -> float:
        segs = self.segments()
        return segs[-1].end if segs else 0.0

    def wall_to_offset(self, wall_ts: float) -> float:
        return wall_ts - (self.started_at or wall_ts)

    def _prune(self) -> None:
        """Ring buffer: delete segments older than retain_seconds (keeps disk bounded on long streams)."""
        if not self.retain_seconds:
            return
        segs = self.segments()
        if not segs:
            return
        cutoff = segs[-1].end - self.retain_seconds
        for s in segs:
            if s.end < cutoff and s.path.exists():
                s.path.unlink(missing_ok=True)


def read_segment_list(list_path: str | Path) -> list[Segment]:
    p = Path(list_path)
    if not p.exists():
        return []
    out: list[Segment] = []
    with p.open(newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 3:
                continue
            try:
                out.append(Segment(path=p.parent / row[0], start=float(row[1]), end=float(row[2])))
            except ValueError:
                continue
    # Normalise so the first segment starts at 0 (TS timestamps from Twitch don't).
    if out and out[0].start:
        base = out[0].start
        out = [Segment(s.path, s.start - base, s.end - base) for s in out]
    return out


def grab_frame(
    source: str,
    out_png: str | Path,
    *,
    grid: bool = True,
    at: float = 0.0,
    quality: str = "best",
    ffmpeg: str = "ffmpeg",
    streamlink: str = "streamlink",
) -> dict:
    """Save one frame of a live channel (or local file) with a 10 % grid + labels for measuring facecams.

    `source` is a Twitch channel name, a stream URL, or a local video path.
    """
    if Path(source).exists():
        inp = ["-ss", str(at), "-i", source]
    else:
        url = source if "://" in source else f"https://www.twitch.tv/{source}"
        hls = subprocess.run([streamlink, "--stream-url", url, quality], capture_output=True, text=True, timeout=60)
        stream = hls.stdout.strip().splitlines()[-1] if hls.stdout.strip() else ""
        if hls.returncode != 0 or "://" not in stream:
            raise RuntimeError(f"could not open {url} (offline?): {(hls.stderr or hls.stdout)[-300:]}")
        inp = ["-i", stream]
    vf = "scale=1280:720"
    if grid:
        vf += ",drawgrid=w=iw/10:h=ih/10:t=1:c=yellow@0.7"
        labels = []
        for i in range(1, 10):
            labels.append(f"drawtext=text='{i / 10:.1f}':x={i * 128 + 3}:y=4:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.6")
            labels.append(f"drawtext=text='{i / 10:.1f}':x=4:y={i * 72 + 3}:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.6")
        vf += "," + ",".join(labels)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inp, "-frames:v", "1", "-vf", vf, str(out_png)],
                   check=True, capture_output=True, text=True, timeout=90)
    return {"source": source, "png": str(out_png)}
