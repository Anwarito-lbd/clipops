"""Auto-poster: leaderboard -> two-lane plan -> safety gates -> YouTube / TikTok / Instagram.

Every tick it reads the live session's leaderboard, asks the planner what each account should
post next (FIRST lane = speed, BEST lane = quality, never the same clip twice), and for each
pick runs the gates before publishing:

  1. not on the hold list (`python -m workers.publisher hold <session> <clip_id>`)
  2. veto window elapsed (`veto_seconds`, 0 = post immediately)
  3. video file exists and its SHA-256 was never uploaded before (no duplicate uploads)
  4. Grok writes the copy (falls back to the clipper's post kit)
  5. Grok safety review approves (slurs, sexual content, doxxing, minors, spoilers, misleading titles)
  6. per-account daily quota (planner) and per-platform results logged to posted.json

Everything is logged to <session>/autopost_log.jsonl. Dry-run logs what *would* post.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from workers.live_clipper.planner import load_posted, plan_posts

from .base import PLATFORMS, PostRequest, PostResult, http, load_json, save_json, sha256_file


@dataclass
class AutoPostConfig:
    accounts: dict  # name -> {"lane": "first"|"best", "platforms": {platform: {...}}, "ayrshare_profile_env": str}
    per_account_per_day: int = 10
    first_min_score: float = 60.0
    best_min_score: float = 45.0
    veto_seconds: float = 0.0
    # "final": wait for the captioned clip so Grok reviews the real transcript (safer, ~25 s later)
    # "draft": FIRST lane may post the uncaptioned draft the moment it exists (fastest)
    first_lane_media: str = "final"
    grok_captions: bool = True
    grok_review: bool = True
    require_review: bool = True  # if Grok is unreachable: hold (True) or post anyway (False)
    max_attempts: int = 3
    notify_webhook_env: str = "DISCORD_WEBHOOK_URL"
    dry_run: bool = False
    raw: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path, **overrides) -> "AutoPostConfig":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        grok = d.get("grok") or {}
        cfg = cls(
            accounts=d["accounts"],
            per_account_per_day=int(d.get("per_account_per_day", 10)),
            first_min_score=float(d.get("first_min_score", 60)),
            best_min_score=float(d.get("best_min_score", 45)),
            veto_seconds=float(d.get("veto_seconds", 0)),
            first_lane_media=str(d.get("first_lane_media", "final")),
            grok_captions=bool(grok.get("captions", True)),
            grok_review=bool(grok.get("review", True)),
            require_review=bool(grok.get("require_review", True)),
            notify_webhook_env=d.get("notify_webhook_env", "DISCORD_WEBHOOK_URL"),
            raw=d,
        )
        for k, v in overrides.items():
            if v is not None:
                setattr(cfg, k, v)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.first_lane_media not in ("final", "draft"):
            raise ValueError('first_lane_media must be "final" or "draft"')
        lanes = sorted(a.get("lane") for a in self.accounts.values())
        if lanes != ["best", "first"]:
            raise ValueError('accounts.json needs exactly two accounts: one "lane": "first" and one "lane": "best"')
        for name, acc in self.accounts.items():
            for plat, pc in (acc.get("platforms") or {}).items():
                if plat not in PLATFORMS:
                    raise ValueError(f"{name}: unknown platform {plat!r} (use {PLATFORMS})")
                if pc.get("via", "official") not in ("official", "ayrshare"):
                    raise ValueError(f"{name}.{plat}: via must be official or ayrshare")

    def lane_accounts(self) -> tuple[str, str]:
        first = next(n for n, a in self.accounts.items() if a.get("lane") == "first")
        best = next(n for n, a in self.accounts.items() if a.get("lane") == "best")
        return first, best


def default_publishers(account: str, acc_cfg: dict, opener=None):
    """Build (official {platform: publisher}, ayrshare publisher|None, ayrshare platforms)."""
    from .ayrshare import AyrsharePublisher
    from .instagram import InstagramPublisher
    from .tiktok import TikTokPublisher
    from .youtube import YouTubePublisher

    official, ayr_platforms = {}, []
    for plat, pc in (acc_cfg.get("platforms") or {}).items():
        if pc.get("via", "official") == "ayrshare":
            ayr_platforms.append(plat)
            continue
        token = pc.get("token") or f"secrets/{account}_{plat}.json"
        if plat == "youtube":
            official[plat] = YouTubePublisher(token, privacy=pc.get("privacy", "public"),
                                              audited=bool(pc.get("audited", False)), opener=opener)
        elif plat == "tiktok":
            official[plat] = TikTokPublisher(token, privacy=pc.get("privacy", "PUBLIC_TO_EVERYONE"), opener=opener)
        elif plat == "instagram":
            official[plat] = InstagramPublisher(token, opener=opener)
    ayr = None
    if ayr_platforms:
        env = acc_cfg.get("ayrshare_profile_env")
        ayr = AyrsharePublisher(profile_key=os.environ.get(env) if env else None, opener=opener)
    return official, ayr, ayr_platforms


def template_copy(manifest: dict) -> dict:
    post = manifest.get("post") or {}
    title = post.get("title") or f"{manifest.get('streamer', 'Streamer')}'s GTA 6 moment"
    tags = post.get("hashtags") or ["#GTA6"]
    caption = post.get("caption") or f"{post.get('hook', '')}\n\n{title}\n\n{' '.join(tags)}"
    return {"title": title, "hook": post.get("hook", ""), "caption": caption,
            "tiktok_caption": f"{title} {' '.join(tags)}"[:150],
            "youtube_title": f"{title[:80]} #Shorts", "hashtags": tags}


class AutoPoster:
    def __init__(
        self,
        session_dir: str | Path,
        cfg: AutoPostConfig,
        *,
        publishers: Callable[[str, dict], tuple] | None = None,
        grok=None,
        notify: Callable[[str], None] | None = None,
        now: Callable[[], float] = time.time,
        log: Callable[[str], None] = print,
    ) -> None:
        self.session = Path(session_dir)
        self.cfg = cfg
        self.publishers = publishers or default_publishers
        self.grok = grok
        self.now = now
        self.log = log
        self.notify = notify or self._webhook
        self.posted_path = self.session / "posted.json"
        self.holds_path = self.session / "holds.json"
        self.pending_path = self.session / "pending.json"
        self.attempts: dict[str, int] = {}
        self._dry_seen: set[str] = set()
        self.stop_event = threading.Event()

    # -- state ---------------------------------------------------------------
    def _event(self, kind: str, **data) -> None:
        rec = {"ts": self.now(), "event": kind, **data}
        with (self.session / "autopost_log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def _webhook(self, text: str) -> None:
        url = os.environ.get(self.cfg.notify_webhook_env or "", "")
        if not url:
            return
        try:
            http("POST", url, json_body={"content": text[:1900]}, timeout=10)
        except Exception:
            pass

    def holds(self) -> set[str]:
        return set(load_json(self.holds_path, []))

    def _board(self) -> list[dict]:
        try:
            return load_json(self.session / "leaderboard.json", []) or []
        except json.JSONDecodeError:  # live clipper mid-write; next tick
            return []

    # -- main loop -----------------------------------------------------------
    def tick(self) -> list[dict]:
        board = self._board()
        posted = load_posted(self.posted_path)
        first, best = self.cfg.lane_accounts()
        plan = plan_posts(board, posted, accounts=(first, best), per_account_per_day=self.cfg.per_account_per_day,
                          first_min_score=self.cfg.first_min_score, best_min_score=self.cfg.best_min_score,
                          now=self.now())
        pending = load_json(self.pending_path, {}) or {}
        holds = self.holds()
        done: list[dict] = []
        for item in plan["first_lane"] + plan["best_lane"]:
            cid = item["clip_id"]
            if cid in holds or cid in self._dry_seen:
                continue
            if not item.get("clip") and self.cfg.first_lane_media != "draft":
                continue  # wait for the captioned final + transcript review
            due = pending.get(cid, {}).get("due")
            if due is None:
                due = self.now() + self.cfg.veto_seconds
                pending[cid] = {"due": due, "account": item["account"]}
                if self.cfg.veto_seconds > 0:
                    self.notify(f"⏳ {item['account']} will post in {self.cfg.veto_seconds:.0f}s: "
                                f"{item.get('title')} (score {item.get('score')}). Hold: hold {cid}")
                    self._event("queued", clip_id=cid, account=item["account"], due=due)
            if self.now() < due:
                continue
            res = self.publish_item(item)
            if res.get("final"):
                pending.pop(cid, None)
            done.append(res)
        save_json(self.pending_path, pending)
        return done

    def run(self, *, every: float = 5.0, until: Callable[[], bool] | None = None) -> None:
        self.log(f"autopost: watching {self.session} (dry_run={self.cfg.dry_run}, veto={self.cfg.veto_seconds:.0f}s)")
        while not self.stop_event.is_set():
            try:
                for r in self.tick():
                    self.log(f"autopost: {r['status']} {r['clip_id']} -> {r.get('account')} {r.get('summary', '')}")
            except Exception as exc:  # never let one bad tick kill the poster
                self._event("tick_error", error=str(exc))
                self.log(f"autopost: tick error {exc}")
            if until and until():
                break
            self.stop_event.wait(every)

    # -- one clip -------------------------------------------------------------
    def _manifest(self, item: dict) -> tuple[dict, Path]:
        path = Path(item.get("clip") or item.get("draft"))
        manifest = load_json(path.parent / "clip.json", {}) or {}
        files = manifest.get("files") or {}
        # prefer the captioned final if it exists by now, even for FIRST lane
        video = Path(files.get("clip") or "") if files.get("clip") and Path(files["clip"]).exists() else path
        return manifest, video

    def _hold(self, item: dict, reasons: list[str]) -> dict:
        holds = self.holds() | {item["clip_id"]}
        save_json(self.holds_path, sorted(holds))
        self._event("held", clip_id=item["clip_id"], account=item["account"], reasons=reasons)
        self.notify(f"🛑 held {item['clip_id']} ({item.get('streamer')}): {'; '.join(reasons)}")
        return {"clip_id": item["clip_id"], "account": item["account"], "status": "HELD", "final": True,
                "summary": "; ".join(reasons)}

    def publish_item(self, item: dict) -> dict:
        cid, account = item["clip_id"], item["account"]
        manifest, video = self._manifest(item)
        if not video.exists():
            return {"clip_id": cid, "account": account, "status": "WAITING_FILE", "final": False}
        digest = sha256_file(video)
        if any(p.get("sha256") == digest for p in load_posted(self.posted_path)):
            return self._hold(item, ["identical video already uploaded"])

        copy = template_copy(manifest)
        if self.grok and self.cfg.grok_captions:
            try:
                copy.update(self.grok.write_post(manifest))
            except Exception as exc:
                self._event("grok_write_error", clip_id=cid, error=str(exc))
        if self.grok and self.cfg.grok_review:
            try:
                review = self.grok.review(manifest, copy)
            except Exception as exc:
                review = {"decision": "hold" if self.cfg.require_review else "approve",
                          "reasons": [f"review unavailable: {exc}"]}
            if review["decision"] != "approve":
                return self._hold(item, review.get("reasons") or ["Grok review"])
        elif self.cfg.require_review and self.cfg.grok_review:
            return self._hold(item, ["review required but Grok not configured (set XAI_API_KEY)"])

        acc_cfg = self.cfg.accounts[account]
        platforms = list((acc_cfg.get("platforms") or {}).keys())
        if self.cfg.dry_run:
            self._dry_seen.add(cid)
            self._event("dry_run", clip_id=cid, account=account, platforms=platforms, video=str(video), copy=copy)
            return {"clip_id": cid, "account": account, "status": "DRY_RUN", "final": True,
                    "summary": f"{platforms} '{copy['title']}' ({video.name})"}

        req_base = dict(clip_id=cid, video_path=str(video), hashtags=copy.get("hashtags") or [],
                        account=account, streamer=manifest.get("streamer", ""),
                        cover_path=(manifest.get("files") or {}).get("thumb"))
        official, ayr, ayr_platforms = self.publishers(account, acc_cfg)
        results: list[PostResult] = []
        for plat, pub in official.items():
            title = copy["youtube_title"] if plat == "youtube" else copy["title"]
            caption = copy["tiktok_caption"] if plat == "tiktok" else copy["caption"]
            try:
                results.append(pub.publish(PostRequest(title=title, caption=caption, **req_base)))
            except Exception as exc:
                results.append(PostResult(plat, False, error=str(exc)))
        if ayr and ayr_platforms:
            try:
                results += ayr.publish_many(PostRequest(title=copy["youtube_title"], caption=copy["caption"],
                                                        **req_base), ayr_platforms)
            except Exception as exc:
                results += [PostResult(p, False, via="ayrshare", error=str(exc)) for p in ayr_platforms]

        ok = [r for r in results if r.ok]
        self._event("published" if ok else "failed", clip_id=cid, account=account,
                    results=[r.to_dict() for r in results])
        if ok:
            posted = load_posted(self.posted_path)
            posted.append({"clip_id": cid, "streamer": manifest.get("streamer", ""), "account": account,
                           "posted_at": self.now(), "sha256": digest, "title": copy["title"],
                           "results": [r.to_dict() for r in results]})
            save_json(self.posted_path, posted)
            links = ", ".join(f"{r.platform}: {r.url or r.post_id} ({r.visibility})" for r in ok)
            fails = ", ".join(f"{r.platform}: {r.error}" for r in results if not r.ok)
            self.notify(f"✅ {account} posted {manifest.get('streamer')}: {copy['title']}\n{links}"
                        + (f"\n⚠️ {fails}" if fails else ""))
            return {"clip_id": cid, "account": account, "status": "POSTED", "final": True, "summary": links
                    + (f" | failed: {fails}" if fails else "")}
        self.attempts[cid] = self.attempts.get(cid, 0) + 1
        errs = "; ".join(f"{r.platform}: {r.error}" for r in results)
        if self.attempts[cid] >= self.cfg.max_attempts:
            return self._hold(item, [f"all platforms failed {self.attempts[cid]}x: {errs}"])
        return {"clip_id": cid, "account": account, "status": "RETRY", "final": False, "summary": errs}
