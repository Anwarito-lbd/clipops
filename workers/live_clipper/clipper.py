"""Live clipper: record the stream, watch chat, cut a captioned 9:16 clip when chat explodes.

    Streamlink records it -> chat counted every 10 s -> chat spikes (fires mid-bucket)
      -> FFmpeg cuts 30 s -> draft out in seconds -> Whisper adds captions -> ranked final clip

Built to be FIRST (early spike trigger, 2 s segments, draft before captions) and to
surface the BEST clips (0-100 rank from chat, audio, speech and the game profile,
refined live as chat keeps reacting; see ranking.py and profiles.py).

Clips land in `<out>/clips/<id>/` with status PENDING_REVIEW plus a post kit
(title, hook, hashtags). Nothing is posted automatically: you review and post.
"""

from __future__ import annotations

import contextlib
import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .chat import write_chat_jsonl
from .cutter import (
    CAPTION_MARGIN, build_ass, chunk_words, cut_window, extract_thumbnail, render_vertical, segment_input,
)
from .profiles import GameProfile, classify_moment, get_profile, post_kit
from .ranking import audio_excitement, leaderboard, score_clip, suggested_caption
from .recorder import Segment, SegmentRecorder
from .spikes import ChatMessage, ChatSpikeDetector, Spike

AUTOMATION_BOUNDARY = "human_approval_manual_posting"
RIGHTS_NOTE = (
    "Clip streamers who allow clipping (most big streamers welcome it; some run paid clip programs). "
    "Keep clips reaction-led and short, never upload full cutscenes or leaked content. Review before posting."
)


@dataclass
class ClipperConfig:
    bucket_seconds: float = 10.0
    segment_seconds: float = 2.0  # small recording segments = footage on disk sooner
    clip_seconds: float = 30.0
    tail_seconds: float = 6.0  # footage kept after chat confirms the spike (the reaction)
    min_messages: int = 8
    ratio_threshold: float = 2.5
    z_threshold: float = 2.5
    max_p_value: float = 1e-4
    cooldown_seconds: float = 45.0
    baseline_buckets: int = 18
    warmup_buckets: int = 3
    layout: str = "blur"  # blur | crop | split
    facecam: tuple[float, float, float, float] | None = None  # split layout cam rect (x, y, w, h) fractions
    captions: bool = True
    draft: bool = True  # uncaptioned draft first so you can post fastest
    whisper_model: str = "tiny"
    whisper_prompt: str | None = None
    device: str = "cpu"
    compute_type: str = "int8"
    max_clips: int | None = None
    retain_seconds: float | None = 1800.0  # ring buffer for long streams
    profile: str = "default"
    hype_terms: tuple[str, ...] = ()

    def apply_profile(self, profile: GameProfile, explicit: Iterable[str] = ()) -> "ClipperConfig":
        """Copy profile tuning onto this config, except fields the user set explicitly."""
        explicit = set(explicit)
        for name in ("ratio_threshold", "z_threshold", "min_messages", "cooldown_seconds",
                     "clip_seconds", "tail_seconds", "whisper_prompt"):
            val = getattr(profile, name)
            if val is not None and name not in explicit:
                setattr(self, name, val)
        self.profile = profile.name
        self.hype_terms = tuple(dict.fromkeys((*profile.hype_terms, *self.hype_terms)))
        return self

    def detector(self, origin: float | None = None) -> ChatSpikeDetector:
        prof = get_profile(self.profile)
        return ChatSpikeDetector(
            bucket_seconds=self.bucket_seconds,
            baseline_buckets=self.baseline_buckets,
            warmup_buckets=self.warmup_buckets,
            min_messages=self.min_messages,
            ratio_threshold=self.ratio_threshold,
            z_threshold=self.z_threshold,
            max_p_value=self.max_p_value,
            cooldown_seconds=self.cooldown_seconds,
            origin=origin,
            extra_hype_terms=self.hype_terms,
            categories={c.name: c.regex for c in prof.categories},
        )


def clip_window(detect_offset: float, cfg: ClipperConfig, available_until: float | None = None) -> tuple[float, float]:
    """Clip ends `tail_seconds` after chat confirmed the spike; the rest is the build-up + moment."""
    end = detect_offset + cfg.tail_seconds
    start = end - cfg.clip_seconds
    if start < 0:
        start, end = 0.0, cfg.clip_seconds
    if available_until is not None and end > available_until:
        end = available_until
        start = max(0.0, end - cfg.clip_seconds)
    return round(start, 3), round(end, 3)


def _transcribe_words(video: Path, out_json: Path, cfg: ClipperConfig) -> tuple[list[dict], str]:
    try:
        from workers.transcription.transcribe import transcribe_video
    except Exception as exc:  # pragma: no cover - import path issue
        return [], f"unavailable: {exc}"
    res = transcribe_video(
        str(video), str(out_json), model=cfg.whisper_model, device=cfg.device,
        compute_type=cfg.compute_type, enable_diarization=False, initial_prompt=cfg.whisper_prompt,
    )
    engine = res.get("engine", "none")
    if engine == "heuristic":  # never burn placeholder text as captions
        return [], "heuristic (no speech engine) — captions skipped"
    words = res.get("word_segments") or []
    if not words:
        for seg in res.get("segments", []):
            words.extend(seg.get("words") or [])
    return words, engine


def rerank(manifest: dict, sustain: dict, profile: GameProfile) -> bool:
    """Recompute moment + score with fresher chat data. Returns True if anything changed."""
    if manifest.get("status") == "FAILED":
        return False
    captions = manifest.get("captions")
    transcript = " ".join(c["text"] for c in captions or [])
    moment = classify_moment(profile, transcript, counts=sustain.get("categories") or manifest["spike"].get("categories"))
    rank = score_clip(manifest["spike"], sustain, manifest.get("audio") or {}, captions, moment["weight"])
    changed = rank != manifest.get("rank") or moment != manifest.get("moment")
    manifest.update(sustain=sustain, moment=moment, rank=rank)
    hook = manifest.get("post", {}).get("hook") or suggested_caption(
        captions, manifest["spike"]["top_terms"], None, manifest["spike"].get("top_messages"))
    manifest["post"] = post_kit(profile, manifest.get("streamer", ""), moment, hook)
    return changed


def _write_post(d: Path, manifest: dict) -> None:
    post = manifest.get("post") or {}
    lines = [f"TITLE: {post.get('title', '')}", f"HOOK:  {post.get('hook', '')}",
             f"SCORE: {manifest.get('rank', {}).get('score')} ({manifest.get('moment', {}).get('category')})", "",
             post.get("caption", ""), "", manifest.get("rights_note", "")]
    (d / "post.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_spike(
    *,
    spike: Spike,
    detect_offset: float,
    segments: list[Segment],
    clips_dir: Path,
    cfg: ClipperConfig,
    source: str,
    streamer: str = "",
    detected_wall: float | None = None,
    sustain: dict | None = None,
    on_draft: Callable[[dict], None] | None = None,
) -> dict:
    """Cut -> draft -> captions -> final render -> rank -> post kit. Manifest is written to clip.json."""
    profile = get_profile(cfg.profile)
    available = segments[-1].end if segments else None
    start, end = clip_window(detect_offset, cfg, available)
    clip_id = f"clip_{int(start):06d}s"
    d = clips_dir / clip_id
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    ref = detected_wall if detected_wall is not None else t0
    manifest: dict = {
        "clip_id": clip_id,
        "streamer": streamer,
        "profile": profile.name,
        "source": source,
        "status": "PENDING_REVIEW",
        "automation_boundary": AUTOMATION_BOUNDARY,
        "rights_note": RIGHTS_NOTE,
        "window": {"start": start, "end": end, "duration": round(end - start, 3)},
        "spike": {**spike.to_dict(), "offset": round(detect_offset, 3)},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "latency": {},
        "error": None,
    }
    try:
        files: dict = {}
        if cfg.draft:
            # Fastest path to something postable: one ultrafast pass straight from the recorded segments.
            src, offset = segment_input(segments, start, end)
            draft = d / "draft.mp4"
            render_vertical(src, draft, layout=cfg.layout, facecam=cfg.facecam, preset="ultrafast",
                            loudnorm=False, seek=(offset, end - start))
            files["draft"] = str(draft)
            manifest["files"] = dict(files)
            manifest["latency"]["spike_to_draft"] = round(time.time() - ref, 2)
            # Provisional chat-only rank so the leaderboard (and auto-poster) see the clip right away.
            manifest["post"] = {"hook": suggested_caption(None, spike.top_terms, None, spike.top_messages)}
            rerank(manifest, sustain or {"seconds": 0.0, "messages": spike.count, "final": False,
                                         "categories": spike.categories}, profile)
            manifest["stage"] = "draft"
            (d / "clip.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            if on_draft:
                on_draft(dict(manifest))
        raw = d / "raw.mp4"
        manifest["cut"] = cut_window(segments, start, end, raw)
        manifest["latency"]["spike_to_cut"] = round(time.time() - ref, 2)
        files["raw"] = str(raw)
        ass = None
        if cfg.captions:
            words, engine = _transcribe_words(raw, d / "transcript.json", cfg)
            manifest["caption_engine"] = engine
            chunks = chunk_words(words)
            if chunks:
                ass = d / "captions.ass"
                ass.write_text(build_ass(chunks, margin_v=CAPTION_MARGIN.get(cfg.layout, 500)), encoding="utf-8")
                manifest["captions"] = [{"start": s, "end": e, "text": t} for s, e, t in chunks]
        out = d / "clip.mp4"
        manifest["render"] = render_vertical(raw, out, ass_path=ass, layout=cfg.layout, facecam=cfg.facecam)
        files["clip"] = str(out)
        manifest["audio"] = audio_excitement(raw)
        peak = manifest["audio"].get("peak_at")
        thumb_at = peak if peak is not None else (end - start) / 2
        extract_thumbnail(out, d / "thumb.jpg", at=min(max(0.0, thumb_at), max(0.0, end - start - 0.2)))
        files["thumb"] = str(d / "thumb.jpg")
        manifest["files"] = files
        hook = suggested_caption(manifest.get("captions"), spike.top_terms, peak, spike.top_messages)
        manifest["post"] = {"hook": hook}  # transcript-based hook replaces the chat-based draft hook
        rerank(manifest, sustain or {"seconds": 0.0, "messages": spike.count, "final": False,
                                     "categories": spike.categories}, profile)
        manifest["latency"]["spike_to_final"] = round(time.time() - ref, 2)
        manifest["stage"] = "final"
        _write_post(d, manifest)
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        manifest["status"] = "FAILED"
        manifest["error"] = f"{exc} {stderr[-800:]}".strip()
    manifest["processing_seconds"] = round(time.time() - t0, 2)
    (d / "clip.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


class LiveClipper:
    """Run recorder + chat reader + spike detector + clip worker until the stream ends."""

    def __init__(
        self,
        *,
        recorder: SegmentRecorder,
        chat: Callable[[threading.Event], Iterator[ChatMessage]],
        out_dir: str | Path,
        cfg: ClipperConfig | None = None,
        source: str = "",
        streamer: str = "",
        on_event: Callable[[str, dict], None] | None = None,
        stop_event: threading.Event | None = None,
        render_slots: threading.Semaphore | None = None,
    ) -> None:
        self.rec, self.chat, self.cfg = recorder, chat, cfg or ClipperConfig()
        # Shared across channels: caps concurrent FFmpeg/Whisper work so the first clips finish fast
        # instead of every channel's renders slowing each other down.
        self.render_slots = render_slots
        self.profile = get_profile(self.cfg.profile)
        self.out = Path(out_dir)
        self.clips_dir = self.out / "clips"
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.chat_log = self.out / "chat.jsonl"
        self.source, self.streamer = source, streamer
        self.on_event = on_event or (lambda kind, data: None)
        self.stop_event = stop_event or threading.Event()
        self.detector: ChatSpikeDetector | None = None
        self.clips: list[dict] = []
        self._spikes: dict[str, Spike] = {}
        self._lock = threading.Lock()
        self._msgs: queue.Queue[ChatMessage] = queue.Queue()
        self._jobs: queue.Queue[tuple[Spike, float] | None] = queue.Queue()

    # -- threads -----------------------------------------------------------
    def _chat_thread(self) -> None:
        batch: list[ChatMessage] = []
        last_flush = time.time()
        for m in self.chat(self.stop_event):
            self._msgs.put(m)
            batch.append(m)
            if time.time() - last_flush > 2:
                write_chat_jsonl(self.chat_log, batch)
                batch, last_flush = [], time.time()
        write_chat_jsonl(self.chat_log, batch)

    def _worker(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            spike, offset = job
            _, need_end = clip_window(offset, self.cfg)
            # Wait only until the recording reaches the end of the window (2 s segments).
            while self.rec.recorded_until() < need_end and self.rec.alive():
                time.sleep(0.2)
            with self._lock:
                sustain = self.detector.sustain(spike) if self.detector else None
            with self.render_slots or contextlib.nullcontext():
                manifest = process_spike(
                    spike=spike, detect_offset=offset, segments=self.rec.segments(), clips_dir=self.clips_dir,
                    cfg=self.cfg, source=self.source, streamer=self.streamer, detected_wall=spike.detected_at,
                    sustain=sustain, on_draft=lambda m, sp=spike: self._on_draft(m, sp),
                )
            manifest["ready_while_live"] = self.rec.alive()
            with self._lock:
                self._spikes[manifest["clip_id"]] = spike
                self.clips = [c for c in self.clips if c["clip_id"] != manifest["clip_id"]]  # drop the draft entry
                self.clips.append(manifest)
                self._save(manifest)
            self.on_event("clip", manifest)
            self._write_status()

    def _on_draft(self, manifest: dict, spike: Spike) -> None:
        with self._lock:
            self._spikes[manifest["clip_id"]] = spike
            self.clips.append(manifest)
        self.on_event("draft", manifest)
        self._write_status()

    def _save(self, manifest: dict) -> None:
        d = self.clips_dir / manifest["clip_id"]
        (d / "clip.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if manifest.get("status") != "FAILED":
            _write_post(d, manifest)

    def _refresh_ranks(self) -> None:
        """Chat keeps reacting after a clip is cut: update sustain + score until it settles."""
        if not self.detector:
            return
        with self._lock:
            for m in self.clips:
                if m.get("status") == "FAILED" or (m.get("rank") or {}).get("final"):
                    continue
                spike = self._spikes.get(m["clip_id"])
                if spike and rerank(m, self.detector.sustain(spike), self.profile):
                    self._save(m)

    def leaderboard(self) -> list[dict]:
        with self._lock:
            return leaderboard(self.clips)

    def _write_status(self) -> None:
        self._refresh_ranks()
        with self._lock:
            status = {
                "streamer": self.streamer,
                "profile": self.profile.name,
                "source": self.source,
                "recording": self.rec.alive(),
                "recorded_until": self.rec.recorded_until(),
                "started_at": self.rec.started_at,
                "buckets": self.detector.bucket_series() if self.detector else [],
                "spikes": [s.to_dict() for s in (self.detector.spikes if self.detector else [])],
                "leaderboard": leaderboard(self.clips),
                "automation_boundary": AUTOMATION_BOUNDARY,
            }
        (self.out / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (self.out / "leaderboard.json").write_text(json.dumps(status["leaderboard"], indent=2), encoding="utf-8")

    # -- main loop ---------------------------------------------------------
    def run(self, *, max_seconds: float | None = None) -> list[dict]:
        self.rec.start()
        threading.Thread(target=self._chat_thread, daemon=True).start()
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        t_start = time.time()
        last_status = 0.0
        queued = 0
        try:
            while not self.stop_event.is_set():
                if self.rec.started_at and self.detector is None:
                    self.detector = self.cfg.detector(origin=self.rec.started_at)
                    self.on_event("recording", {"started_at": self.rec.started_at, "streamer": self.streamer})
                spikes: list[Spike] = []
                with self._lock:
                    while True:
                        try:
                            m = self._msgs.get_nowait()
                        except queue.Empty:
                            break
                        if self.detector and m.ts >= (self.rec.started_at or 0):
                            spikes += self.detector.add(m)
                    if self.detector:
                        spikes += self.detector.tick(time.time())
                for sp in spikes:
                    if self.cfg.max_clips is not None and queued >= self.cfg.max_clips:
                        break
                    offset = self.rec.wall_to_offset(sp.detected_at)
                    self.on_event("spike", {**sp.to_dict(), "offset": round(offset, 2), "streamer": self.streamer})
                    queued += 1
                    self._jobs.put((sp, offset))
                if time.time() - last_status > 2:
                    self._write_status()
                    last_status = time.time()
                if not self.rec.alive() and self.rec.started_at is not None:
                    self.on_event("stream_ended", {"recorded_until": self.rec.recorded_until(), "streamer": self.streamer})
                    break
                if self.rec.started_at is None and not self.rec.alive():
                    raise RuntimeError(f"recorder exited before writing any segment: {self.rec.error_output()}")
                if max_seconds and time.time() - t_start > max_seconds:
                    break
                time.sleep(0.1)
        finally:
            self.rec.stop()
            self._jobs.put(None)
            worker.join()
            if self.detector:
                with self._lock:
                    self.detector.flush()
            self._write_status()
            self.stop_event.set()
        return self.clips


def replay_vod(
    *,
    video: str | Path,
    messages: Iterable[ChatMessage],
    out_dir: str | Path,
    cfg: ClipperConfig | None = None,
    streamer: str = "",
    on_event: Callable[[str, dict], None] | None = None,
) -> dict:
    """Offline mode: same detector, cutter and ranking over a finished VOD + chat log (ts = s from VOD start)."""
    cfg = cfg or ClipperConfig()
    profile = get_profile(cfg.profile)
    on_event = on_event or (lambda kind, data: None)
    out = Path(out_dir)
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    dur = float(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], text=True
        ).strip()
    )
    segments = [Segment(path=Path(video).resolve(), start=0.0, end=dur)]
    det = cfg.detector(origin=0.0)
    for m in sorted(messages, key=lambda m: m.ts):
        det.add(m)
    det.flush()
    spikes = det.spikes
    # Pre-rank by chat alone so --max-clips keeps the strongest moments.
    pre = sorted(spikes, key=lambda s: score_clip(s.to_dict(), det.sustain(s), {}, None)["score"], reverse=True)
    if cfg.max_clips is not None:
        pre = pre[: cfg.max_clips]
    clips = []
    for sp in sorted(pre, key=lambda s: s.bucket_start):
        on_event("spike", {**sp.to_dict(), "streamer": streamer})
        m = process_spike(
            spike=sp, detect_offset=sp.detected_at, segments=segments, clips_dir=clips_dir, cfg=cfg,
            source=str(video), streamer=streamer, sustain=det.sustain(sp),
        )
        on_event("clip", m)
        clips.append(m)
    board = leaderboard(clips)
    summary = {
        "source": str(video),
        "streamer": streamer,
        "profile": profile.name,
        "duration": dur,
        "config": {f.name: getattr(cfg, f.name) for f in fields(cfg)},
        "buckets": det.bucket_series(),
        "spikes": [s.to_dict() for s in spikes],
        "clips": clips,
        "leaderboard": board,
        "automation_boundary": AUTOMATION_BOUNDARY,
    }
    (out / "status.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out / "leaderboard.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
    return summary


def detect_only(messages: Iterable[ChatMessage], cfg: ClipperConfig, origin: float | None = None):
    """Run just the detector with a config's tuning (CLI `spikes` command)."""
    det = cfg.detector(origin=origin)
    for m in sorted(messages, key=lambda m: m.ts):
        det.add(m)
    det.flush()
    return det.spikes, det


__all__ = [
    "AUTOMATION_BOUNDARY", "ClipperConfig", "LiveClipper", "clip_window", "detect_only",
    "process_spike", "replay_vod", "rerank",
]
