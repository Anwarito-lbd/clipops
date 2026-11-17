"""CLI: python -m workers.live_clipper {live,replay,spikes} ...

  live CHANNEL [CHANNEL ...] --profile gta6
                               watch one or many live Twitch streams at once, auto-clip chat
                               spikes, rank them, keep a combined leaderboard
  live sim --simulate-video vod.mp4 --simulate-chat chat.jsonl
                               same pipeline in real time from local files (testing)
  replay VIDEO CHAT.jsonl      clip a finished VOD from its chat log
  spikes CHAT.jsonl            print msgs/10s buckets + detected spikes (threshold tuning)
  scout                        who is live in the GTA VI category right now, by viewers
  live --scout 5 --profile gta6
                               auto-pick the 5 biggest live GTA VI channels and clip them all
  plan SESSION_DIR             posting queue for 2 accounts (FIRST lane / BEST lane), daily quotas
  plan SESSION_DIR --mark clip_000123s --account A     log that you posted it

Per-streamer facecam boxes for --layout split go in a JSON file (--streamers):
  {"kaicenat": {"facecam": [0.0, 0.0, 0.26, 0.30]}, "caseoh_": {"facecam": [0.74, 0.70, 0.26, 0.30]}}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.live_clipper.chat import TwitchChatReader, load_chat_jsonl, replay_chat_realtime  # noqa: E402
from workers.live_clipper.clipper import ClipperConfig, LiveClipper, detect_only, replay_vod  # noqa: E402
from workers.live_clipper.profiles import PROFILES, get_profile  # noqa: E402
from workers.live_clipper.planner import load_posted, mark_posted, plan_posts  # noqa: E402
from workers.live_clipper.ranking import leaderboard  # noqa: E402
from workers.live_clipper.recorder import SegmentRecorder  # noqa: E402

# argparse dest -> ClipperConfig field (defaults are None so we know what the user set explicitly)
TUNING = {
    "bucket": "bucket_seconds", "segment": "segment_seconds", "clip_seconds": "clip_seconds",
    "tail": "tail_seconds", "min_msgs": "min_messages", "ratio": "ratio_threshold", "z": "z_threshold",
    "cooldown": "cooldown_seconds", "warmup": "warmup_buckets", "layout": "layout", "model": "whisper_model",
    "device": "device", "compute_type": "compute_type", "max_clips": "max_clips",
}


def _add_tuning(p: argparse.ArgumentParser) -> None:
    p.add_argument("--profile", choices=sorted(PROFILES), default="default",
                   help="game profile (gta6 = launch-night vocabulary, moments, thresholds)")
    g = p.add_argument_group("detection / clip tuning (profile sets sensible defaults)")
    g.add_argument("--bucket", type=float, help="chat bucket seconds (default 10)")
    g.add_argument("--segment", type=float, help="recording segment seconds (default 2)")
    g.add_argument("--clip-seconds", type=float)
    g.add_argument("--tail", type=float, help="seconds kept after chat confirms the spike")
    g.add_argument("--min-msgs", type=int)
    g.add_argument("--ratio", type=float, help="bucket must be >= ratio x baseline")
    g.add_argument("--z", type=float, help="bucket must be >= z robust std-devs above baseline")
    g.add_argument("--cooldown", type=float)
    g.add_argument("--warmup", type=int, help="buckets of history before detection starts")
    g.add_argument("--hype", action="append", default=[], help="extra hype term (repeatable)")
    g.add_argument("--layout", choices=["blur", "crop", "split"])
    g.add_argument("--facecam", help="split layout cam box x,y,w,h as fractions, e.g. 0,0,0.26,0.3")
    g.add_argument("--no-captions", action="store_true")
    g.add_argument("--no-draft", action="store_true", help="skip the fast uncaptioned draft")
    g.add_argument("--model", help="whisper model: tiny/base/small/medium/large-v3 (default tiny)")
    g.add_argument("--device", help="cpu or cuda")
    g.add_argument("--compute-type")
    g.add_argument("--max-clips", type=int)


def _facecam(text: str | None):
    if not text:
        return None
    vals = tuple(float(v) for v in text.split(","))
    if len(vals) != 4:
        raise SystemExit("--facecam needs x,y,w,h")
    return vals


def _cfg(a: argparse.Namespace, *, facecam=None, channel: str | None = None) -> ClipperConfig:
    cfg = ClipperConfig(hype_terms=tuple(a.hype))
    explicit = []
    for dest, field_name in TUNING.items():
        val = getattr(a, dest, None)
        if val is not None:
            setattr(cfg, field_name, val)
            explicit.append(field_name)
    cfg.apply_profile(get_profile(a.profile), explicit)
    cfg.captions = not a.no_captions
    cfg.draft = not a.no_draft
    cfg.facecam = facecam or _facecam(a.facecam)
    if cfg.layout == "split" and not cfg.facecam:
        if channel is None:
            raise SystemExit("--layout split needs --facecam x,y,w,h (or a --streamers file entry)")
        print(f"  {channel}: no facecam box in --streamers, using blur layout for this channel", flush=True)
        cfg.layout = "blur"
    if cfg.device == "cuda" and a.compute_type is None:
        cfg.compute_type = "float16"
    return cfg


class Printer:
    def __init__(self) -> None:
        self.lock = threading.Lock()

    def __call__(self, kind: str, data: dict) -> None:
        stamp = time.strftime("%H:%M:%S")
        who = f"[{data.get('streamer')}] " if data.get("streamer") else ""
        with self.lock:
            if kind == "spike":
                when = "mid-bucket" if data.get("early") else "bucket close"
                print(f"[{stamp}] {who}CHAT SPIKE  {data['count']} msgs ({when}; baseline {data['baseline']}, "
                      f"x{data['ratio']}) chat: {data['top_terms']} {data.get('categories') or ''}", flush=True)
            elif kind == "draft":
                print(f"[{stamp}] {who}DRAFT READY {data['files']['draft']}  "
                      f"({data['latency'].get('spike_to_draft')}s after spike)", flush=True)
            elif kind == "clip":
                if data["status"] == "FAILED":
                    print(f"[{stamp}] {who}CLIP FAILED {data['clip_id']}: {data['error']}", flush=True)
                    return
                live = " — stream still LIVE" if data.get("ready_while_live") else ""
                r, mo, post = data.get("rank", {}), data.get("moment", {}), data.get("post", {})
                spoiler = "  [SPOILER RISK]" if mo.get("spoiler_risk") else ""
                print(f"[{stamp}] {who}CLIP READY  score {r.get('score')} ({mo.get('category') or 'general'}){spoiler}"
                      f"  {data['files']['clip']}  ({data['latency'].get('spike_to_final')}s after spike){live}\n"
                      f"           title: {post.get('title')}\n           hook:  {post.get('hook')}", flush=True)
            elif kind == "recording":
                print(f"[{stamp}] {who}recording started", flush=True)
            elif kind == "stream_ended":
                print(f"[{stamp}] {who}stream ended at {data['recorded_until']:.0f}s", flush=True)


def _print_board(board: list[dict], limit: int = 10) -> None:
    if not board:
        print("no clips yet")
        return
    print("\nBEST CLIPS")
    for row in board[:limit]:
        who = f"{row.get('streamer')}: " if row.get("streamer") else ""
        print(f"  #{row['position']:<2} {row['score']:>5}  {who}{row.get('title')}  -> {row.get('clip')}")


def _run_live(a: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    printer = Printer()
    stop = threading.Event()
    session = Path(a.out_dir or f"storage/live/{a.profile}-{time.strftime('%Y%m%d-%H%M%S')}")
    streamers_file = json.loads(Path(a.streamers).read_text(encoding="utf-8")) if a.streamers else {}
    # Either a flat {channel: {...}} map or {"channels": {...}, "waves": {"au": [...], "us": [...]}}
    streamers = streamers_file.get("channels", streamers_file)
    if a.wave:
        waves = streamers_file.get("waves") or {}
        if a.wave not in waves:
            ap.error(f"--wave {a.wave!r} not in {a.streamers} (have: {sorted(waves)})")
        a.channels = list(dict.fromkeys([*a.channels, *waves[a.wave]]))
    if a.scout and not a.simulate_video:
        from workers.live_clipper.scout import TwitchScout, pick_channels

        live = TwitchScout().top_streams(first=50, language=a.language)
        picked = pick_channels(live, top=a.scout, exclude={c.lower() for c in a.channels})
        for s in live:
            if s["channel"] in picked:
                print(f"  scouted {s['channel']:<20} {s['viewers']:>8,} viewers  {s['title'][:60]}", flush=True)
        a.channels = list(dict.fromkeys([*a.channels, *picked]))
    if not a.channels:
        ap.error("give channel names and/or --scout N")
    clippers: list[LiveClipper] = []
    slots = a.render_slots or max(1, (os.cpu_count() or 2) // 2)
    render_slots = threading.Semaphore(slots)

    if a.simulate_video:
        cfg = _cfg(a)
        rec = SegmentRecorder(session / "sim" / "segments", source_file=a.simulate_video, segment_seconds=cfg.segment_seconds)
        sim_msgs = load_chat_jsonl(a.simulate_chat) if a.simulate_chat else []

        def chat_source(ev: threading.Event, rec=rec):
            while rec.started_at is None and not ev.is_set():  # align chat t=0 with recording t=0
                time.sleep(0.05)
            yield from replay_chat_realtime(sim_msgs, ev, start_wall=rec.started_at)
            ev.wait()

        clippers.append(LiveClipper(recorder=rec, chat=chat_source, out_dir=session / "sim", cfg=cfg,
                                    source=f"simulated:{a.simulate_video}", streamer=a.channels[0],
                                    on_event=printer, stop_event=stop, render_slots=render_slots))
    else:
        for ch in a.channels:
            if "://" in ch:
                ap.error("pass Twitch channel names (e.g. kaicenat), not URLs")
            name = ch.lower()
            cfg = _cfg(a, facecam=tuple(streamers.get(name, {}).get("facecam") or ()) or None, channel=name)
            rec = SegmentRecorder(session / name / "segments", stream_url=f"https://www.twitch.tv/{name}",
                                  quality=a.quality, segment_seconds=cfg.segment_seconds, retain_seconds=a.retain)
            clippers.append(LiveClipper(recorder=rec, chat=TwitchChatReader(name).messages, out_dir=session / name,
                                        cfg=cfg, source=f"https://www.twitch.tv/{name}", streamer=name,
                                        on_event=printer, stop_event=stop, render_slots=render_slots))

    print(f"Live clipper [{a.profile}] -> {session}  watching: {', '.join(a.channels)}  "
          f"(max {slots} clip renders at once)\n"
          "Clips are ranked and queued for YOUR review; nothing is auto-posted. Ctrl+C to stop.", flush=True)
    def run_one(c: LiveClipper) -> None:
        try:
            c.run(max_seconds=a.max_seconds)
        except Exception as exc:  # one bad channel must not stop the others
            with printer.lock:
                sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] [{c.streamer}] STOPPED: {exc}\n")
                sys.stdout.flush()

    threads = [threading.Thread(target=run_one, args=(c,), daemon=True) for c in clippers]
    for t in threads:
        t.start()

    def combined() -> list[dict]:
        rows = [row for c in clippers for row in c.leaderboard()]
        rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
        for i, row in enumerate(rows, 1):
            row["position"] = i
        return rows

    try:
        while any(t.is_alive() for t in threads):
            (session / "leaderboard.json").write_text(json.dumps(combined(), indent=2), encoding="utf-8")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nstopping…", flush=True)
        stop.set()
        for t in threads:
            t.join(timeout=120)
    board = combined()
    session.mkdir(parents=True, exist_ok=True)
    (session / "leaderboard.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
    _print_board(board)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="live_clipper", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_live = sub.add_parser("live", help="clip live streams while they're still live")
    p_live.add_argument("channels", nargs="*", help="Twitch channel name(s)")
    p_live.add_argument("--scout", type=int, default=0, help="also auto-pick the top N live channels in the category")
    p_live.add_argument("--language", default=None, help="scout filter, e.g. en")
    p_live.add_argument("--quality", default="best")
    p_live.add_argument("--out-dir", default=None)
    p_live.add_argument("--streamers", help="JSON file with per-streamer settings (facecam boxes) and waves")
    p_live.add_argument("--wave", help="add the channels of this wave from --streamers (e.g. au, us)")
    p_live.add_argument("--render-slots", type=int, default=None,
                        help="max clips rendering at once across all channels (default: CPU cores / 2)")
    p_live.add_argument("--max-seconds", type=float, default=None, help="stop after N seconds")
    p_live.add_argument("--retain", type=float, default=1800.0, help="keep only the last N seconds of segments")
    p_live.add_argument("--simulate-video", default=None, help="replay this file as if it were live")
    p_live.add_argument("--simulate-chat", default=None, help="replay this chat.jsonl (ts from 0) in real time")
    _add_tuning(p_live)

    p_rep = sub.add_parser("replay", help="clip a finished VOD from its chat log")
    p_rep.add_argument("video")
    p_rep.add_argument("chat", help="chat.jsonl with ts in seconds from VOD start (or epoch + --chat-start)")
    p_rep.add_argument("--chat-start", type=float, default=0.0, help="epoch time of VOD start if chat ts are epoch")
    p_rep.add_argument("--streamer", default="")
    p_rep.add_argument("--out-dir", default="storage/live/replay")
    _add_tuning(p_rep)

    p_sp = sub.add_parser("spikes", help="analyse a chat log only")
    p_sp.add_argument("chat")
    p_sp.add_argument("--chat-start", type=float, default=0.0)
    _add_tuning(p_sp)

    p_snap = sub.add_parser("snapshot", help="grab a frame per channel with a grid to measure facecam boxes")
    p_snap.add_argument("sources", nargs="+", help="Twitch channel names (or local video files)")
    p_snap.add_argument("--out-dir", default="storage/snapshots")
    p_snap.add_argument("--at", type=float, default=0.0, help="seek seconds (local files only)")

    p_sc = sub.add_parser("scout", help="list live channels in the GTA VI category by viewers")
    p_sc.add_argument("--top", type=int, default=20)
    p_sc.add_argument("--language", default=None)
    p_sc.add_argument("--category", default=None, help="override category name (default: Grand Theft Auto VI)")

    p_pl = sub.add_parser("plan", help="posting queue for two accounts from a live session's leaderboard")
    p_pl.add_argument("session", help="session dir (the one holding leaderboard.json)")
    p_pl.add_argument("--accounts", default="A,B", help="FIRST-lane,BEST-lane account names")
    p_pl.add_argument("--per-account", type=int, default=10, help="posts per account per day")
    p_pl.add_argument("--first-min", type=float, default=60.0, help="min score for the speed lane")
    p_pl.add_argument("--best-min", type=float, default=45.0, help="min score for the quality lane")
    p_pl.add_argument("--allow-spoilers", action="store_true")
    p_pl.add_argument("--mark", help="clip_id you just posted")
    p_pl.add_argument("--account", help="account you posted --mark on")

    a = ap.parse_args(argv)

    if a.cmd == "snapshot":
        from workers.live_clipper.recorder import grab_frame

        out = Path(a.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        failed = 0
        for src in a.sources:
            name = Path(src).stem if Path(src).exists() else src.lower()
            try:
                res = grab_frame(src, out / f"{name}.png", at=a.at)
                print(f"{name}: {res['png']}")
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                failed += 1
                print(f"{name}: FAILED {exc}")
        print('Read the facecam box off the yellow grid as fractions -> "facecam": [x, y, w, h] in your streamers file.')
        return 1 if failed else 0

    if a.cmd == "scout":
        from workers.live_clipper.scout import GTA6_CATEGORY_NAMES, TwitchScout

        names = (a.category,) if a.category else GTA6_CATEGORY_NAMES
        rows = TwitchScout().top_streams(names=names, first=a.top, language=a.language)
        for i, r in enumerate(rows, 1):
            print(f"#{i:<3} {r['channel']:<22} {r['viewers']:>9,} viewers  [{r['language']}] {r['title'][:70]}")
        if not rows:
            print("nobody live in that category right now")
        return 0

    if a.cmd == "plan":
        session = Path(a.session)
        posted_path = session / "posted.json"
        accounts = tuple(x.strip() for x in a.accounts.split(","))
        if len(accounts) != 2:
            ap.error("--accounts takes exactly two names, e.g. A,B")
        board = json.loads((session / "leaderboard.json").read_text(encoding="utf-8"))
        if a.mark:
            if a.account not in accounts:
                ap.error(f"--account must be one of {accounts}")
            row = next((r for r in board if r["clip_id"] == a.mark), {})
            mark_posted(posted_path, a.mark, a.account, streamer=row.get("streamer", ""))
            print(f"logged {a.mark} on {a.account}")
            return 0
        plan = plan_posts(board, load_posted(posted_path), accounts=accounts, per_account_per_day=a.per_account,
                          first_min_score=a.first_min, best_min_score=a.best_min, allow_spoilers=a.allow_spoilers)
        print(f"{plan['day']}  posts left today: {plan['quota_left']}")
        for lane, label in (("first_lane", f"FIRST lane -> {accounts[0]} (post now, speed wins)"),
                            ("best_lane", f"BEST lane -> {accounts[1]} (captioned, rotate streamers)")):
            print(f"\n{label}")
            for r in plan[lane]:
                path = r.get("draft") if r.get("post") == "draft" else r.get("clip")
                extra = f"  also: {', '.join(r['same_moment_streamers'])}" if r.get("same_moment_streamers") else ""
                print(f"  {r['score']:>5}  {r.get('streamer')}: {r.get('title')}\n         {path}{extra}")
            if not plan[lane]:
                print("  (nothing above the cut-off yet)")
        if plan["held_for_spoilers"]:
            print(f"\nheld (spoiler risk): {', '.join(plan['held_for_spoilers'])}")
        (session / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return 0

    if a.cmd == "live":
        return _run_live(a, ap)

    cfg = _cfg(a)
    if a.cmd == "spikes":
        msgs = load_chat_jsonl(a.chat, time_offset=a.chat_start)
        spikes, det = detect_only(msgs, cfg, origin=min((m.ts for m in msgs), default=0.0))
        series = det.bucket_series()
        peak = max((b["count"] for b in series), default=1)
        hits = {s.bucket_start for s in spikes}
        for b in series:
            bar = "#" * max(0, round(40 * b["count"] / max(peak, 1)))
            print(f"{b['start'] - series[0]['start']:8.0f}s {b['count']:5d} {bar}{'  <-- SPIKE' if b['start'] in hits else ''}")
        print(json.dumps([{**s.to_dict(), "sustain": det.sustain(s)} for s in spikes], indent=2))
        return 0

    msgs = load_chat_jsonl(a.chat, time_offset=a.chat_start)
    summary = replay_vod(video=a.video, messages=msgs, out_dir=a.out_dir, cfg=cfg, streamer=a.streamer, on_event=Printer())
    print(f"{len(summary['spikes'])} spikes, {sum(c['status'] != 'FAILED' for c in summary['clips'])} clips "
          f"-> {a.out_dir}/clips (PENDING_REVIEW; you post manually)")
    _print_board(leaderboard(summary["clips"]))
    return 0 if all(c["status"] != "FAILED" for c in summary["clips"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
