"""CLI: python -m workers.publisher {doctor,auth,post,autopost,hold,unhold,grok-test}

  doctor [--accounts accounts.json]       check every tool, key and token; prints how to fix each
  auth youtube   --account A              browser consent -> secrets/A_youtube.json
  auth tiktok    --account A              prints the TikTok consent URL, paste back the redirect URL
  auth instagram --account A --short-token TOKEN   long-lived token + IG business id
  post CLIP_DIR --account A               post one clip now (try --dry-run first)
  autopost SESSION_DIR                    keep posting the best clips of a live session
  hold SESSION_DIR CLIP_ID                never post this clip (works during the veto window)
  grok-test                               list Grok models and run a sample caption + review
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # .env at repo root holds the keys
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from workers.publisher.autopost import AutoPostConfig, AutoPoster  # noqa: E402
from workers.publisher.base import load_json, save_json  # noqa: E402

DEFAULT_ACCOUNTS = "accounts.json"


def _grok_or_none(verbose: bool = True):
    if not os.environ.get("XAI_API_KEY"):
        return None
    from workers.publisher.grok import Grok

    try:
        return Grok()
    except Exception as exc:
        if verbose:
            print(f"Grok disabled: {exc}")
        return None


# -- doctor -------------------------------------------------------------------------------
def doctor(accounts_path: str | None) -> int:
    rows: list[tuple[bool, str, str]] = []

    def check(ok: bool, name: str, fix: str = "") -> None:
        if all(r[1] != name for r in rows):
            rows.append((bool(ok), name, fix))

    check(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (>= 3.10)", "install Python 3.11+")
    ff = shutil.which("ffmpeg")
    check(ff, "ffmpeg on PATH", "Windows: winget install Gyan.FFmpeg | macOS: brew install ffmpeg | Linux: apt install ffmpeg")
    if ff:
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        check(" subtitles " in filters, "ffmpeg has libass (burned captions)", "install a full ffmpeg build (gyan.dev 'full')")
    check(shutil.which("ffprobe"), "ffprobe on PATH", "comes with ffmpeg")
    from workers.live_clipper.recorder import streamlink_cmd

    check(streamlink_cmd(), "streamlink (records Twitch)", "pip install streamlink")
    has_fw = importlib.util.find_spec("faster_whisper") is not None
    check(has_fw, "faster-whisper (captions)", "pip install faster-whisper")
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    cached = sorted(p.name.replace("models--Systran--faster-whisper-", "") for p in hub.glob("models--Systran--faster-whisper-*"))
    check(cached, f"Whisper model downloaded ({', '.join(cached) or 'none'})",
          "run scripts/setup_live_clipper so it downloads before launch")
    for env, why, fix in (
        ("TWITCH_CLIENT_ID", "Twitch scout", "dev.twitch.tv/console/apps -> Register (category: Analytics)"),
        ("TWITCH_CLIENT_SECRET", "Twitch scout", "same app -> New Secret"),
        ("XAI_API_KEY", "Grok captions + safety review", "console.x.ai -> API keys"),
    ):
        check(os.environ.get(env), f"{env} ({why})", f"add to .env — {fix}")
    grok = _grok_or_none(verbose=False)
    if grok:
        try:
            models = [m for m in grok.models() if m.startswith("grok")]
            check(models, f"Grok reachable, models: {', '.join(models[:4])}", "check XAI_API_KEY")
        except Exception as exc:
            check(False, "Grok reachable", str(exc)[:120])

    if accounts_path and Path(accounts_path).exists():
        try:
            cfg = AutoPostConfig.load(accounts_path)
            check(True, f"{accounts_path} valid (FIRST={cfg.lane_accounts()[0]}, BEST={cfg.lane_accounts()[1]})")
            for name, acc in cfg.accounts.items():
                for plat, pc in (acc.get("platforms") or {}).items():
                    if pc.get("via") == "ayrshare":
                        check(os.environ.get("AYRSHARE_API_KEY"), "AYRSHARE_API_KEY (YouTube/TikTok/IG via Ayrshare)",
                              "ayrshare.com -> API key; link the account in their dashboard")
                        env = acc.get("ayrshare_profile_env")
                        if env:
                            check(os.environ.get(env), f"{name}: {env} (Ayrshare profile key)", "Ayrshare -> User Profiles")
                    else:
                        tok = pc.get("token") or f"secrets/{name}_{plat}.json"
                        check(Path(tok).exists(), f"{name}.{plat} official token {tok}",
                              f"python -m workers.publisher auth {plat} --account {name}")
                        if plat in ("youtube", "tiktok") and not pc.get("audited"):
                            rows.append((True, f"{name}.{plat}: official API posts PRIVATE until your app is audited",
                                         "set \"via\": \"ayrshare\" for public posts now; apply for the audit"))
        except Exception as exc:
            check(False, f"{accounts_path}", str(exc))
    else:
        check(False, f"accounts file {accounts_path or DEFAULT_ACCOUNTS}",
              "cp workers/publisher/accounts.example.json accounts.json and edit")

    width = max(len(r[1]) for r in rows)
    bad = 0
    for ok, name, fix in rows:
        bad += not ok
        print(f"{'OK ' if ok else 'XX '} {name:<{width}}  {'' if ok else '-> ' + fix}")
    print(f"\n{len(rows) - bad}/{len(rows)} checks passed")
    return 0 if bad == 0 else 1


# -- commands ------------------------------------------------------------------------------
def cmd_auth(a: argparse.Namespace) -> int:
    token = a.token or f"secrets/{a.account}_{a.platform}.json"
    Path(token).parent.mkdir(parents=True, exist_ok=True)
    if a.platform == "youtube":
        from workers.publisher.youtube import authorize

        secrets_file = a.client_secrets or os.environ.get("YOUTUBE_CLIENT_SECRETS", "secrets/youtube_client_secret.json")
        print(json.dumps(authorize(secrets_file, token), indent=2))
    elif a.platform == "tiktok":
        from workers.publisher.tiktok import auth_url, exchange_code

        key, secret = os.environ.get("TIKTOK_CLIENT_KEY", ""), os.environ.get("TIKTOK_CLIENT_SECRET", "")
        redirect = os.environ.get("TIKTOK_REDIRECT_URI", "")
        if not (key and secret and redirect):
            print("set TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI in .env")
            return 1
        url, _state = auth_url(key, redirect)
        print(f"1) Log in as the TikTok account for {a.account} and open:\n{url}\n"
              "2) After approving, copy the FULL address bar URL you were redirected to and paste it here.")
        pasted = input("redirect URL: ").strip()
        print(json.dumps(exchange_code(key, secret, pasted, redirect, token), indent=2))
    elif a.platform == "instagram":
        from workers.publisher.instagram import exchange_token

        app_id, app_secret = os.environ.get("META_APP_ID", ""), os.environ.get("META_APP_SECRET", "")
        if not (app_id and app_secret and a.short_token):
            print("need META_APP_ID + META_APP_SECRET in .env and --short-token from Graph API Explorer "
                  "(permissions: instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement)")
            return 1
        print(json.dumps(exchange_token(app_id, app_secret, a.short_token, token), indent=2))
    return 0


def cmd_post(a: argparse.Namespace) -> int:
    cfg = AutoPostConfig.load(a.accounts, dry_run=a.dry_run or None)
    clip_dir = Path(a.clip_dir)
    manifest = load_json(clip_dir / "clip.json")
    if not manifest:
        print(f"no clip.json in {clip_dir}")
        return 1
    if a.account not in cfg.accounts:
        print(f"unknown account {a.account}; have {list(cfg.accounts)}")
        return 1
    if a.no_review:
        cfg.grok_review = cfg.require_review = False
    files = manifest.get("files") or {}
    item = {"clip_id": manifest["clip_id"], "account": a.account, "clip": files.get("clip"), "draft": files.get("draft"),
            "streamer": manifest.get("streamer"), "title": (manifest.get("post") or {}).get("title"),
            "score": (manifest.get("rank") or {}).get("score")}
    session = clip_dir.parent.parent
    poster = AutoPoster(session, cfg, grok=_grok_or_none())
    print(json.dumps(poster.publish_item(item), indent=2))
    return 0


def cmd_autopost(a: argparse.Namespace) -> int:
    cfg = AutoPostConfig.load(a.accounts, dry_run=a.dry_run or None, veto_seconds=a.veto)
    grok = _grok_or_none()
    if (cfg.grok_review or cfg.grok_captions) and not grok:
        print("note: XAI_API_KEY not set — Grok captions/review off"
              + (" and clips will be HELD (require_review=true)" if cfg.require_review and cfg.grok_review else ""))
    poster = AutoPoster(a.session, cfg, grok=grok)
    try:
        poster.run(every=a.every)
    except KeyboardInterrupt:
        print("autopost stopped")
    return 0


def cmd_hold(a: argparse.Namespace, add: bool) -> int:
    path = Path(a.session) / "holds.json"
    holds = set(load_json(path, []))
    holds = holds | {a.clip_id} if add else holds - {a.clip_id}
    save_json(path, sorted(holds))
    print(f"{'held' if add else 'released'} {a.clip_id}; holds: {sorted(holds)}")
    return 0


def cmd_grok_test() -> int:
    grok = _grok_or_none()
    if not grok:
        print("set XAI_API_KEY in .env")
        return 1
    print("models:", ", ".join(m for m in grok.models() if m.startswith("grok")))
    sample = {"streamer": "kaicenat", "moment": {"category": "chase", "spoiler_risk": False},
              "captions": [{"text": "NO WAY the cops are everywhere bro"}],
              "spike": {"top_messages": ["5 STARS LMAO", "SWAT INCOMING"]},
              "post": {"title": "kaicenat's first police chase in GTA 6 went crazy", "hook": "SWAT INCOMING"},
              "rank": {"score": 82}}
    copy = grok.write_post(sample)
    print("model:", grok.model)
    print("copy:", json.dumps(copy, indent=2))
    print("review:", json.dumps(grok.review(sample, copy), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publisher", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("doctor")
    p.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    p = sub.add_parser("auth")
    p.add_argument("platform", choices=["youtube", "tiktok", "instagram"])
    p.add_argument("--account", required=True)
    p.add_argument("--token", help="token file (default secrets/<account>_<platform>.json)")
    p.add_argument("--client-secrets", help="YouTube OAuth client_secret.json")
    p.add_argument("--short-token", help="Instagram: short-lived user token from Graph API Explorer")
    p = sub.add_parser("post")
    p.add_argument("clip_dir")
    p.add_argument("--account", required=True)
    p.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-review", action="store_true", help="skip Grok review for this manual post")
    p = sub.add_parser("autopost")
    p.add_argument("session")
    p.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--veto", type=float, default=None, help="seconds to wait before posting (hold window)")
    p.add_argument("--every", type=float, default=5.0)
    for name in ("hold", "unhold"):
        p = sub.add_parser(name)
        p.add_argument("session")
        p.add_argument("clip_id")
    sub.add_parser("grok-test")
    a = ap.parse_args(argv)
    if a.cmd == "doctor":
        return doctor(a.accounts)
    if a.cmd == "auth":
        return cmd_auth(a)
    if a.cmd == "post":
        return cmd_post(a)
    if a.cmd == "autopost":
        return cmd_autopost(a)
    if a.cmd in ("hold", "unhold"):
        return cmd_hold(a, add=a.cmd == "hold")
    if a.cmd == "grok-test":
        return cmd_grok_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
