"""Live chat-spike clipper: chat parsing, spike detection, captions, and an FFmpeg replay run."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.live_clipper.chat import load_chat_jsonl, parse_irc_line  # noqa: E402
from workers.live_clipper.clipper import ClipperConfig, clip_window, replay_vod  # noqa: E402
from workers.live_clipper.cutter import build_ass, chunk_words, vertical_filter  # noqa: E402
from workers.live_clipper.profiles import GTA6, classify_moment, get_profile, post_kit  # noqa: E402
from workers.live_clipper.ranking import score_clip  # noqa: E402
from workers.live_clipper.recorder import read_segment_list  # noqa: E402
from workers.live_clipper.spikes import ChatMessage, ChatSpikeDetector, detect_spikes  # noqa: E402


def _chat(
    baseline_per_10s: float, duration: float, bursts: list[tuple[float, int]], seed: int = 1,
    burst_texts: tuple[str, ...] = ("HE DID NOT LETS GO",),
) -> list[ChatMessage]:
    rng = random.Random(seed)
    msgs, t = [], 0.0
    while True:
        t += rng.expovariate(baseline_per_10s / 10.0)
        if t >= duration:
            break
        msgs.append(ChatMessage(ts=t, user=f"u{rng.randint(0, 999)}", text="hello chat"))
    for at, n in bursts:
        for _ in range(n):
            msgs.append(ChatMessage(ts=at + rng.random() * 9.9, user=f"u{rng.randint(0, 999)}", text=rng.choice(burst_texts)))
    return sorted(msgs, key=lambda m: m.ts)


def test_parse_irc_privmsg_with_tags_uses_server_timestamp():
    line = "@badge-info=;display-name=CoolGuy;tmi-sent-ts=1700000000123 :coolguy!coolguy@coolguy.tmi.twitch.tv PRIVMSG #xqc :HE DID NOT\r\n"
    m = parse_irc_line(line)
    assert m is not None
    assert m.user == "coolguy" and m.text == "HE DID NOT"
    assert m.ts == pytest.approx(1700000000.123)


def test_parse_irc_ignores_non_messages():
    assert parse_irc_line("PING :tmi.twitch.tv") is None
    assert parse_irc_line(":tmi.twitch.tv 001 justinfan123 :Welcome, GLHF!") is None
    m = parse_irc_line(":bob!bob@bob.tmi.twitch.tv PRIVMSG #chan :hi: there", now=5.0)
    assert m.ts == 5.0 and m.text == "hi: there"


def test_detector_finds_burst_once_and_respects_cooldown():
    msgs = _chat(4, 180, bursts=[(90, 50), (100, 45)])  # two adjacent exploding buckets
    spikes, det = detect_spikes(msgs, origin=0.0)
    assert len(spikes) == 1
    sp = spikes[0]
    assert sp.bucket_start == 90.0
    # fires mid-bucket as soon as thresholds clear, not at the 100 s bucket close
    assert sp.early and 90.0 < sp.detected_at < 95.0
    assert sp.ratio >= 2.5 and sp.zscore >= 2.5 and sp.p_value <= 1e-4
    assert "LETS" in sp.top_terms or "DID" in sp.top_terms
    assert len(det.bucket_series()) == 18
    sus = det.sustain(sp)
    assert sus["buckets"] == 2 and sus["messages"] >= 90 and sus["final"]


def test_detector_quiet_chat_and_warmup_produce_no_spikes():
    spikes, _ = detect_spikes(_chat(5, 300, bursts=[]), origin=0.0)
    assert spikes == []
    # a burst inside the warm-up window has no baseline yet
    spikes, _ = detect_spikes(_chat(3, 60, bursts=[(10, 40)]), origin=0.0)
    assert spikes == []


def test_detector_caps_single_user_spam():
    msgs = _chat(4, 120, bursts=[])
    msgs += [ChatMessage(ts=70 + i * 0.1, user="spambot", text="W") for i in range(80)]
    spikes, _ = detect_spikes(sorted(msgs, key=lambda m: m.ts), origin=0.0)
    assert spikes == []


def test_tick_closes_buckets_when_chat_goes_silent():
    det = ChatSpikeDetector(origin=0.0)
    det.add(ChatMessage(ts=1.0, user="a", text="hi"))
    det.tick(95.0)
    assert len(det.closed) == 9 and det.closed[0].count == 1 and det.closed[5].count == 0


def test_clip_window_ends_shortly_after_detection_and_clamps():
    cfg = ClipperConfig(clip_seconds=30, tail_seconds=6)
    assert clip_window(92.7, cfg) == (68.7, 98.7)  # build-up + moment, then 6 s of reaction
    assert clip_window(5.0, cfg) == (0.0, 30.0)
    assert clip_window(92.7, cfg, available_until=95.0) == (65.0, 95.0)


def test_chunk_words_keeps_whisper_continuations_and_sentence_breaks():
    words = [
        {"word": " they", "start": 0.0, "end": 0.2}, {"word": " lose", "start": 0.2, "end": 0.4},
        {"word": " 80", "start": 0.4, "end": 0.6}, {"word": "%", "start": 0.6, "end": 0.7},
        {"word": " of", "start": 0.7, "end": 0.8}, {"word": " viewers.", "start": 0.8, "end": 1.2},
        {"word": " He", "start": 1.3, "end": 1.4}, {"word": " did", "start": 1.4, "end": 1.5},
        {"word": " not", "start": 1.5, "end": 1.7},
    ]
    texts = [t for _, _, t in chunk_words(words)]
    assert texts == ["they lose 80%", "of viewers.", "He did not"]


def test_build_ass_uppercases_and_escapes():
    ass = build_ass([(0.0, 1.0, "he did {not}")])
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Clip" in ass
    assert "HE DID (NOT)" in ass
    assert "PlayResY: 1920" in ass


def test_read_segment_list_normalises_twitch_timestamps(tmp_path):
    (tmp_path / "segments.csv").write_text("seg_000000.ts,1234.5,1244.5\nseg_000001.ts,1244.5,1254.5\n")
    segs = read_segment_list(tmp_path / "segments.csv")
    assert [(s.start, s.end) for s in segs] == [(0.0, 10.0), (10.0, 20.0)]


def test_load_chat_jsonl_applies_offset(tmp_path):
    p = tmp_path / "chat.jsonl"
    p.write_text(json.dumps({"ts": 1000.5, "user": "a", "text": "W"}) + "\n")
    assert load_chat_jsonl(p, time_offset=1000.0)[0].ts == pytest.approx(0.5)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_replay_vod_renders_vertical_clip_for_chat_spike(tmp_path):
    vod = tmp_path / "vod.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=80",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=80", "-shortest",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(vod)],
        check=True,
    )
    msgs = _chat(3, 80, bursts=[(50, 45)], burst_texts=("5 STARS LMAO", "COPS EVERYWHERE", "WANTED LEVEL", "LETS GOOO"))
    cfg = ClipperConfig(captions=False, clip_seconds=12, tail_seconds=4).apply_profile(get_profile("gta6"))
    cfg.clip_seconds, cfg.tail_seconds = 12, 4
    summary = replay_vod(video=vod, messages=msgs, out_dir=tmp_path / "out", cfg=cfg, streamer="kaicenat")
    assert len(summary["spikes"]) == 1
    clip = summary["clips"][0]
    assert clip["status"] == "PENDING_REVIEW", clip["error"]
    assert clip["automation_boundary"] == "human_approval_manual_posting"
    sp = clip["spike"]
    assert sp["early"] and 50.0 < sp["detected_at"] < 60.0
    assert clip["window"]["end"] == pytest.approx(sp["detected_at"] + 4, abs=0.01)
    assert clip["window"]["duration"] == pytest.approx(12.0)
    assert 0 < clip["rank"]["score"] <= 100 and clip["rank"]["final"]
    assert clip["moment"]["category"] == "chase"
    assert "kaicenat" in clip["post"]["title"] and "#GTA6" in clip["post"]["hashtags"]
    assert (Path(clip["files"]["clip"]).parent / "post.txt").read_text().startswith("TITLE:")
    assert Path(clip["files"]["draft"]).stat().st_size > 0
    assert summary["leaderboard"][0]["clip_id"] == clip["clip_id"]
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-show_entries", "format=duration", "-of", "json", clip["files"]["clip"]],
        text=True,
    )
    info = json.loads(out)
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (1080, 1920)
    assert float(info["format"]["duration"]) == pytest.approx(12.0, abs=0.2)
    assert Path(clip["files"]["thumb"]).stat().st_size > 0


def test_gta6_profile_tunes_config_but_respects_explicit_flags():
    cfg = ClipperConfig(ratio_threshold=4.0).apply_profile(GTA6, explicit=["ratio_threshold"])
    assert cfg.profile == "gta6"
    assert cfg.ratio_threshold == 4.0  # user flag wins
    assert cfg.min_messages == 15 and cfg.z_threshold == 3.0
    assert "vice city" in cfg.hype_terms and "Leonida" in (cfg.whisper_prompt or "")


def test_gta6_moments_classify_chase_glitch_and_flag_story_spoilers():
    assert classify_moment(GTA6, "bro we got five stars, cops everywhere")["category"] == "chase"
    assert classify_moment(GTA6, "", counts={"glitch": 30, "funny": 12})["category"] == "glitch"
    story = classify_moment(GTA6, "Lucia in that cutscene, what a twist")
    assert story["category"] == "story" and story["spoiler_risk"]
    kit = post_kit(GTA6, "kaicenat", story, "NO WAY")
    assert kit["spoiler_risk"] and "no spoilers" in kit["title"].lower()


def test_gta6_detector_counts_moment_categories_in_chat():
    cfg = ClipperConfig().apply_profile(GTA6)
    msgs = _chat(4, 120, bursts=[(80, 60)], burst_texts=("WASTED LMAO", "he got BUSTED", "5 stars", "COPS"))
    det = cfg.detector(origin=0.0)
    for m in msgs:
        det.add(m)
    det.flush()
    assert len(det.spikes) == 1
    cats = det.sustain(det.spikes[0])["categories"]
    assert cats.get("chase", 0) > 0 and cats.get("fail", 0) > 0


def test_ranking_prefers_big_sustained_loud_chase_over_small_story_blip():
    big = score_clip({"ratio": 12, "zscore": 25, "hype_ratio": 0.7, "count": 300},
                     {"seconds": 40, "messages": 1200}, {"ok": True, "jump_db": 14},
                     [{"start": 0, "end": 2, "text": "NO WAY bro what!"}], moment_weight=1.0)
    small = score_clip({"ratio": 2.6, "zscore": 3.1, "hype_ratio": 0.1, "count": 20},
                       {"seconds": 10, "messages": 20}, {"ok": True, "jump_db": 2}, None, moment_weight=0.5)
    assert big["score"] > 85 > 40 > small["score"]


def test_split_layout_stacks_facecam_over_gameplay():
    vf = vertical_filter("split", facecam=(0.0, 0.0, 0.25, 0.3))
    assert "crop=iw*0.25:ih*0.3:iw*0.0:ih*0.0" in vf and "vstack" in vf


class _FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_scout_ranks_live_gta6_channels_by_viewers():
    from workers.live_clipper.scout import TwitchScout, pick_channels

    calls = []

    def opener(req, timeout=20):
        calls.append(req.full_url)
        if "oauth2/token" in req.full_url:
            return _FakeResp({"access_token": "tok"})
        if "/games?" in req.full_url:
            assert req.headers["Authorization"] == "Bearer tok"
            return _FakeResp({"data": [{"id": "999", "name": "Grand Theft Auto VI"}]})
        assert "game_id=999" in req.full_url
        return _FakeResp({"data": [
            {"user_login": "lacy", "viewer_count": 40000, "title": "GTA 6 24/7", "language": "en"},
            {"user_login": "kaicenat", "viewer_count": 600000, "title": "GTA 6 DAY 1", "language": "en"},
            {"user_login": "tiny", "viewer_count": 12, "title": "gta", "language": "en"},
        ]})

    rows = TwitchScout("id", "secret", opener=opener).top_streams(first=10)
    assert [r["channel"] for r in rows] == ["kaicenat", "lacy", "tiny"]
    assert pick_channels(rows, top=5, min_viewers=100) == ["kaicenat", "lacy"]
    assert pick_channels(rows, top=1, exclude={"kaicenat"}) == ["lacy"]


def _row(cid, streamer, score, moment, t, *, final=True, spoiler=False):
    return {"clip_id": cid, "streamer": streamer, "score": score, "moment": moment, "detected_at": t,
            "final": final, "spoiler_risk": spoiler, "clip": f"/c/{cid}.mp4", "draft": f"/d/{cid}.mp4",
            "title": f"{streamer} {moment}"}


def test_planner_splits_lanes_dedupes_same_moment_and_respects_quota(tmp_path):
    from workers.live_clipper.planner import load_posted, mark_posted, plan_posts

    now = 1_800_000_000.0
    rows = [
        _row("k1", "kaicenat", 90, "chase", now - 300),   # same chase moment, three streamers
        _row("s1", "ishowspeed", 80, "chase", now - 280),
        _row("l1", "lacy", 70, "chase", now - 260),
        _row("k2", "kaicenat", 75, "glitch", now - 100),
        _row("s2", "ishowspeed", 50, "funny", now - 50),
        _row("x1", "kaicenat", 95, "story", now - 10, spoiler=True),
    ]
    plan = plan_posts(rows, [], per_account_per_day=10, now=now)
    first_ids = [r["clip_id"] for r in plan["first_lane"]]
    best_ids = [r["clip_id"] for r in plan["best_lane"]]
    assert first_ids == ["k1", "k2"]  # best clip per moment only
    assert plan["first_lane"][0]["same_moment_streamers"] == ["ishowspeed", "lacy"]
    assert set(best_ids) == {"s1", "l1", "s2"} and not set(best_ids) & set(first_ids)
    assert "x1" not in first_ids + best_ids and plan["held_for_spoilers"] == ["x1"]

    posted = tmp_path / "posted.json"
    mark_posted(posted, "k1", "A", now=now)
    plan2 = plan_posts(rows, load_posted(posted), per_account_per_day=1, now=now)
    assert plan2["quota_left"] == {"A": 0, "B": 1}
    assert plan2["first_lane"] == [] and len(plan2["best_lane"]) == 1
    assert all(r["clip_id"] not in {"k1", "s1", "l1"} or r["account"] == "B" for r in plan2["best_lane"])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_snapshot_grid_frame_from_local_file(tmp_path):
    from workers.live_clipper.recorder import grab_frame

    vid = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:duration=2",
                    "-c:v", "libx264", "-preset", "ultrafast", str(vid)], check=True)
    out = grab_frame(str(vid), tmp_path / "v.png", at=1.0)
    assert Path(out["png"]).stat().st_size > 0


def test_gta6_streamers_file_has_waves_and_known_channels():
    cfg = json.loads((ROOT / "workers" / "live_clipper" / "gta6_streamers.json").read_text())
    assert set(cfg["waves"]) == {"au", "us"}
    assert {"kaicenat", "ishowspeed", "lacy", "darkviperau"} <= set(cfg["channels"])
    for wave in cfg["waves"].values():
        assert all(ch in cfg["channels"] for ch in wave)
