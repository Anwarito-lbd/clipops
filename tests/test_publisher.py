"""Publishers (YouTube / TikTok / Instagram / Ayrshare), Grok, and the auto-poster's safety gates.

No network: a scripted opener plays the platform APIs and records every request.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.publisher.autopost import AutoPostConfig, AutoPoster  # noqa: E402
from workers.publisher.ayrshare import AyrsharePublisher  # noqa: E402
from workers.publisher.base import PostRequest, PostResult, save_json  # noqa: E402
from workers.publisher.grok import Grok, parse_json_reply  # noqa: E402
from workers.publisher.instagram import InstagramPublisher  # noqa: E402
from workers.publisher.tiktok import TikTokPublisher, chunk_plan  # noqa: E402
from workers.publisher.youtube import YouTubePublisher  # noqa: E402


class Resp:
    def __init__(self, body=None, status=200, headers=None):
        self.status, self.headers = status, headers or {}
        self._raw = body if isinstance(body, (bytes, bytearray)) else json.dumps(body if body is not None else {}).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Script:
    """Routes (method, url-substring) -> response; records requests."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        for (method, frag), resp in self.routes:
            if req.get_method() == method and frag in req.full_url:
                return resp(req) if callable(resp) else resp
        raise AssertionError(f"unexpected {req.get_method()} {req.full_url}")


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 1000)
    return p


def _req(video, **kw):
    return PostRequest(clip_id="clip_1", video_path=str(video), title=kw.get("title", "kai's first chase"),
                       caption=kw.get("caption", "SWAT INCOMING #GTA6"), hashtags=["#GTA6", "#Twitch"])


def test_youtube_refreshes_token_and_does_resumable_upload(tmp_path, video):
    tok = tmp_path / "yt.json"
    save_json(tok, {"client_id": "cid", "client_secret": "sec", "refresh_token": "r", "expires_at": 0})
    s = Script([
        (("POST", "oauth2.googleapis.com/token"), Resp({"access_token": "AT", "expires_in": 3600})),
        (("POST", "upload/youtube/v3/videos"), Resp({}, headers={"Location": "https://upload.example/session1"})),
        (("PUT", "upload.example/session1"), Resp({"id": "vid123", "status": {"privacyStatus": "public"}})),
    ])
    res = YouTubePublisher(str(tok), opener=s).publish(_req(video))
    assert res.ok and res.post_id == "vid123" and res.url == "https://youtube.com/shorts/vid123"
    assert "private" in res.visibility  # unaudited project -> YouTube locks it private
    init = s.calls[1]
    meta = json.loads(init.data)
    assert init.headers["Authorization"] == "Bearer AT" and init.headers["X-upload-content-length"] == str(video.stat().st_size)
    assert meta["snippet"]["categoryId"] == "20" and "#Shorts" in meta["snippet"]["description"]
    assert s.calls[2].data == video.read_bytes()
    assert json.loads(tok.read_text())["access_token"] == "AT"  # refreshed token persisted


def test_tiktok_direct_post_picks_allowed_privacy_and_uploads_with_content_range(tmp_path, video):
    tok = tmp_path / "tt.json"
    save_json(tok, {"access_token": "TT", "expires_at": time.time() + 3600})
    statuses = iter([{"data": {"status": "PROCESSING_UPLOAD"}},
                     {"data": {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [7311]}}])
    s = Script([
        (("POST", "creator_info/query"), Resp({"data": {"privacy_level_options": ["SELF_ONLY"]}})),
        (("POST", "video/init"), Resp({"data": {"publish_id": "p1", "upload_url": "https://up.tiktok/u1"},
                                       "error": {"code": "ok"}})),
        (("PUT", "up.tiktok/u1"), Resp({})),
        (("POST", "status/fetch"), lambda req: Resp(next(statuses))),
    ])
    res = TikTokPublisher(str(tok), opener=s, sleep=lambda _s: None).publish(_req(video))
    assert res.ok and res.post_id == "7311" and res.visibility == "self_only"  # unaudited -> only SELF_ONLY offered
    init = json.loads(s.calls[1].data)
    size = video.stat().st_size
    assert init["post_info"]["privacy_level"] == "SELF_ONLY"
    assert init["source_info"] == {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    assert s.calls[2].headers["Content-range"] == f"bytes 0-{size - 1}/{size}"


def test_tiktok_chunk_plan_rules():
    assert chunk_plan(3_000_000) == (3_000_000, 1)
    assert chunk_plan(50 * 2**20) == (50 * 2**20, 1)
    assert chunk_plan(150 * 2**20) == (64 * 2**20, 2)  # last chunk absorbs the remainder


def test_instagram_reel_resumable_upload_poll_and_publish(tmp_path, video):
    tok = tmp_path / "ig.json"
    save_json(tok, {"access_token": "IG", "ig_user_id": "1784", "username": "gtaclips",
                    "expires_at": time.time() + 86400, "version": "v25.0"})
    states = iter([{"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}])
    s = Script([
        (("POST", "/1784/media?"), Resp({"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v25.0/C1"})),
        (("POST", "rupload.facebook.com"), Resp({"success": True})),
        (("GET", "/C1?"), lambda req: Resp(next(states))),
        (("POST", "/1784/media_publish"), Resp({"id": "M9"})),
        (("GET", "/M9?"), Resp({"permalink": "https://instagram.com/reel/abc"})),
    ])
    res = InstagramPublisher(str(tok), opener=s, sleep=lambda _s: None).publish(_req(video))
    assert res.ok and res.post_id == "M9" and res.url == "https://instagram.com/reel/abc"
    assert "media_type=REELS" in s.calls[0].full_url and "upload_type=resumable" in s.calls[0].full_url
    up = s.calls[1]
    assert up.headers["Authorization"] == "OAuth IG" and up.headers["Offset"] == "0"
    assert up.headers["File_size"] == str(video.stat().st_size) and up.data == video.read_bytes()
    assert "creation_id=C1" in s.calls[4].full_url


def test_ayrshare_uploads_media_then_posts_and_maps_per_platform_results(video):
    s = Script([
        (("GET", "media/uploadUrl"), Resp({"uploadUrl": "https://s3/put", "accessUrl": "https://cdn/clip.mp4",
                                           "contentType": "video/mp4"})),
        (("PUT", "s3/put"), Resp({})),
        (("POST", "api.ayrshare.com/api/post"), Resp({"status": "success", "id": "ay1", "postIds": [
            {"platform": "youtube", "status": "success", "id": "yt9", "postUrl": "https://youtu.be/yt9"},
            {"platform": "tiktok", "status": "success", "id": "tt9", "postUrl": "https://tiktok.com/@x/video/tt9"}],
            "errors": [{"platform": "instagram", "message": "reel processing failed"}]})),
    ])
    out = AyrsharePublisher(api_key="K", profile_key="PK", opener=s).publish_many(_req(video), ["youtube", "tiktok", "instagram"])
    by = {r.platform: r for r in out}
    assert by["youtube"].ok and by["youtube"].url == "https://youtu.be/yt9" and by["tiktok"].ok
    assert not by["instagram"].ok and "reel processing failed" in by["instagram"].error
    post = s.calls[2]
    body = json.loads(post.data)
    assert post.headers["Profile-key"] == "PK" and post.headers["Authorization"] == "Bearer K"
    assert body["mediaUrls"] == ["https://cdn/clip.mp4"] and body["youTubeOptions"]["shorts"] is True


def test_grok_picks_model_writes_copy_and_reviews():
    replies = iter([
        '```json\n{"title": "Kai vs SWAT", "hook": "SWAT INCOMING", "caption": "c #GTA6", '
        '"tiktok_caption": "t", "youtube_title": "y #Shorts"}\n```',
        '{"decision": "hold", "reasons": ["streamer shows home address"], "spoiler": false}',
    ])
    s = Script([
        (("GET", "api.x.ai/v1/models"), Resp({"data": [{"id": "grok-4.6"}, {"id": "grok-4.7"}, {"id": "other"}]})),
        (("POST", "chat/completions"), lambda req: Resp({"choices": [{"message": {"content": next(replies)}}]})),
    ])
    g = Grok(api_key="X", opener=s)
    copy = g.write_post({"streamer": "kaicenat", "captions": [{"text": "no way"}]})
    assert g.model == "grok-4.7" and copy["title"] == "Kai vs SWAT"
    review = g.review({"streamer": "kaicenat"}, copy)
    assert review == {"decision": "hold", "reasons": ["streamer shows home address"], "spoiler": False}
    assert json.loads(s.calls[1].data)["response_format"] == {"type": "json_object"}
    assert parse_json_reply('ok here: {"a": 1} thanks') == {"a": 1}


# -- auto-poster -----------------------------------------------------------------------------

class FakePub:
    def __init__(self, plat, fail=False):
        self.plat, self.fail, self.calls = plat, fail, []

    def publish(self, req):
        self.calls.append(req)
        if self.fail:
            raise RuntimeError(f"{self.plat} down")
        return PostResult(self.plat, True, post_id=f"{self.plat}-{req.clip_id}", url=f"https://{self.plat}/{req.clip_id}",
                          visibility="public")


class FakeGrok:
    def __init__(self, decision="approve"):
        self.decision, self.reviewed = decision, []

    def write_post(self, m):
        return {"title": f"GROK {m['streamer']}", "youtube_title": "GROK yt #Shorts", "tiktok_caption": "GROK tt"}

    def review(self, m, copy):
        self.reviewed.append(m["clip_id"])
        return {"decision": self.decision, "reasons": ["spoiler in transcript"] if self.decision == "hold" else []}


def _session(tmp_path, n=4, ages=None):
    rows = []
    now = time.time()
    ages = ages or [100 - i * 10 for i in range(n)]
    for i in range(n):
        cid = f"clip_{i:06d}s"
        d = tmp_path / "kaicenat" / "clips" / cid
        d.mkdir(parents=True)
        (d / "clip.mp4").write_bytes(f"video-{i}".encode() * 100)
        manifest = {"clip_id": cid, "streamer": "kaicenat", "files": {"clip": str(d / "clip.mp4")},
                    "post": {"title": f"t{i}", "hook": "H", "hashtags": ["#GTA6"]}, "rank": {"score": 90 - i * 5}}
        (d / "clip.json").write_text(json.dumps(manifest))
        rows.append({"clip_id": cid, "streamer": "kaicenat", "score": 90 - i * 5, "moment": ["chase", "glitch", "fail", "funny"][i],
                     "detected_at": now - ages[i], "final": True, "spoiler_risk": False,
                     "clip": str(d / "clip.mp4"), "draft": None, "title": f"t{i}"})
    save_json(tmp_path / "leaderboard.json", rows)
    return rows


def _cfg(**kw):
    accounts = {"A": {"lane": "first", "platforms": {"youtube": {}, "tiktok": {}, "instagram": {}}},
                "B": {"lane": "best", "platforms": {"youtube": {}, "instagram": {}}}}
    cfg = AutoPostConfig(accounts=accounts, per_account_per_day=10, **kw)
    cfg.validate()
    return cfg


def _poster(tmp_path, cfg, pubs, grok=FakeGrok(), clock=None):
    clock = clock or [time.time()]

    def factory(account, acc_cfg):
        return {p: pubs[(account, p)] for p in acc_cfg["platforms"]}, None, []

    return AutoPoster(tmp_path, cfg, publishers=factory, grok=grok, notify=lambda _m: None,
                      now=lambda: clock[0], log=lambda _m: None), clock


def _pubs(fail=()):
    return {(a, p): FakePub(p, fail=(a, p) in fail) for a in "AB" for p in ("youtube", "tiktok", "instagram")}


def test_autopost_veto_window_then_posts_both_lanes_with_grok_copy(tmp_path):
    _session(tmp_path, ages=[60, 50, 3600, 7200])  # two fresh moments, two stale ones
    pubs = _pubs()
    poster, clock = _poster(tmp_path, _cfg(veto_seconds=45), pubs)
    assert poster.tick() == []  # queued, inside veto window
    assert all(not p.calls for p in pubs.values())
    clock[0] += 46
    done = poster.tick()
    assert {d["status"] for d in done} == {"POSTED"} and len(done) == 4
    a_posts = [r.clip_id for r in pubs[("A", "youtube")].calls]
    b_posts = [r.clip_id for r in pubs[("B", "youtube")].calls]
    assert a_posts == ["clip_000000s", "clip_000001s"]  # FIRST lane: fresh moments only
    assert sorted(b_posts) == ["clip_000002s", "clip_000003s"]  # BEST lane: the rest
    assert not set(a_posts) & set(b_posts)  # never the same clip on both accounts
    assert pubs[("A", "youtube")].calls[0].title == "GROK yt #Shorts"
    assert pubs[("A", "tiktok")].calls[0].caption == "GROK tt"
    posted = json.loads((tmp_path / "posted.json").read_text())
    assert len(posted) == 4 and all(p["sha256"] for p in posted)
    assert poster.tick() == []  # nothing posted twice


def test_autopost_hold_list_and_grok_hold_and_missing_review(tmp_path):
    _session(tmp_path, n=2)
    save_json(tmp_path / "holds.json", ["clip_000000s"])
    pubs = _pubs()
    poster, _ = _poster(tmp_path, _cfg(), pubs, grok=FakeGrok("hold"))
    done = poster.tick()
    assert [d["status"] for d in done] == ["HELD"] and done[0]["clip_id"] == "clip_000001s"
    assert set(json.loads((tmp_path / "holds.json").read_text())) == {"clip_000000s", "clip_000001s"}
    assert all(not p.calls for p in pubs.values())

    tmp2 = tmp_path / "s2"
    tmp2.mkdir()
    _session(tmp2, n=1)
    poster2, _ = _poster(tmp2, _cfg(), _pubs(), grok=None)
    assert poster2.tick()[0]["summary"].startswith("review required")


def test_autopost_dry_run_publishes_nothing(tmp_path):
    _session(tmp_path, n=2)
    pubs = _pubs()
    poster, _ = _poster(tmp_path, _cfg(dry_run=True), pubs)
    assert {d["status"] for d in poster.tick()} == {"DRY_RUN"}
    assert poster.tick() == []
    assert all(not p.calls for p in pubs.values()) and not (tmp_path / "posted.json").exists()


def test_autopost_partial_failure_still_counts_and_total_failure_retries_then_holds(tmp_path):
    _session(tmp_path, n=1)
    pubs = _pubs(fail={("A", "tiktok")})
    poster, _ = _poster(tmp_path, _cfg(), pubs)
    done = poster.tick()
    assert done[0]["status"] == "POSTED" and "tiktok: tiktok down" in done[0]["summary"]

    tmp2 = tmp_path / "s2"
    tmp2.mkdir()
    _session(tmp2, n=1)
    all_fail = _pubs(fail={("A", p) for p in ("youtube", "tiktok", "instagram")})
    poster2, _ = _poster(tmp2, _cfg(max_attempts=2), all_fail)
    assert poster2.tick()[0]["status"] == "RETRY"
    assert poster2.tick()[0]["status"] == "HELD"


def test_autopost_refuses_identical_video_already_uploaded(tmp_path):
    rows = _session(tmp_path, n=2)
    # second clip's file is byte-identical to the first (e.g. same moment re-cut)
    Path(rows[1]["clip"]).write_bytes(Path(rows[0]["clip"]).read_bytes())
    poster, _ = _poster(tmp_path, _cfg(), _pubs())
    statuses = sorted(d["status"] for d in poster.tick())
    assert statuses == ["HELD", "POSTED"]


def test_accounts_example_is_valid():
    cfg = AutoPostConfig.load(ROOT / "workers" / "publisher" / "accounts.example.json")
    assert cfg.lane_accounts() == ("A", "B") and cfg.veto_seconds == 45
    with pytest.raises(ValueError):
        AutoPostConfig(accounts={"A": {"lane": "first"}, "B": {"lane": "first"}}).validate()
