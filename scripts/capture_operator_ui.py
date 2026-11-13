"""Capture real Playwright screenshots (desktop + mobile) and walkthrough video of ClipOps Operator UI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STUDIO_DIR = ROOT / "apps" / "operator-ui"
OUT_DIR = ROOT / "docs" / "images"
PROOF_DIR = ROOT / "docs" / "proof"

for p in (str(ROOT), str(STUDIO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROOF_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        ws_dir = tmp_path / "studio_ws"
        video_dir = tmp_path / "pw_video"
        video_dir.mkdir(parents=True, exist_ok=True)

        os.environ["CLIPOPS_STUDIO_WORKSPACE"] = str(ws_dir)
        os.environ["REMOTION_URL"] = ""

        from server import app  # noqa: E402

        config = uvicorn.Config(app, host="127.0.0.1", port=8017, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        # Wait for server
        import urllib.request
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8017/api/studio/health", timeout=1) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.25)

        exe = _find_browser()
        launch_kwargs = {"headless": True}
        if exe:
            launch_kwargs["executable_path"] = exe

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                record_video_dir=str(video_dir),
                record_video_size={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page.goto("http://127.0.0.1:8017/", wait_until="networkidle")
            page.wait_for_timeout(800)

            # Step 1: Load the real 3-scene 16:9 Spoken Podcast Example (faster-whisper + PySceneDetect + Hook scoring)
            page.click("#btn-example")
            page.wait_for_selector(".clip-card", timeout=120000)
            page.wait_for_timeout(1200)

            # Step 2: Click a word chip in Transcript & Words to seek inside Scene 2 and show live word highlight
            word_chips = page.locator("#tab-transcript .word-chip")
            if word_chips.count() > 25:
                word_chips.nth(25).click()
            page.wait_for_timeout(1000)

            # Capture primary desktop NLE workspace screenshot (16:9 feed + 9:16 safe guides + V1/A1/T1 timeline + live words)
            page.screenshot(path=str(OUT_DIR / "operator-ui.png"), full_page=False)

            # Step 3: Inspect Hooks & Retention Pacing tab
            page.click('[data-itab="scoring"]')
            page.wait_for_timeout(1200)

            # Step 4: Trigger Dry-Run Filtergraph & inspect FFmpeg + Remotion payload
            page.click("#btn-dry-run")
            page.wait_for_timeout(1200)

            # Step 5: Approve top cut (human gate)
            page.click("#btn-approve")
            page.wait_for_timeout(1000)

            # Step 6: Render Local 9:16 Cut & preview rendered vertical MP4
            page.click("#btn-render")
            page.wait_for_function(
                "() => document.querySelector('#meta-render')?.textContent?.includes('rendered')",
                timeout=60000,
            )
            page.wait_for_timeout(1400)

            # Capture secondary desktop screenshot showing Rendered 9:16 Cut + Filtergraph & Gate
            page.screenshot(path=str(OUT_DIR / "operator-ui-rendered.png"), full_page=False)

            # Mobile 390x844 screenshot in separate clean context without disturbing recorded video
            mob_ctx = browser.new_context(viewport={"width": 390, "height": 844})
            mob_page = mob_ctx.new_page()
            mob_page.goto("http://127.0.0.1:8017/", wait_until="networkidle")
            mob_page.wait_for_selector(".clip-card", timeout=15000)
            mob_page.wait_for_timeout(600)
            mob_page.screenshot(path=str(OUT_DIR / "operator-ui-mobile.png"), full_page=False)
            mob_ctx.close()

            # Close recorded video context so .webm finalizes
            recorded_video = page.video
            ctx.close()
            raw_webm = Path(recorded_video.path())
            browser.close()

            # Save the session summary JSON to docs/proof/studio-demo-summary.json
            with urllib.request.urlopen("http://127.0.0.1:8017/api/studio/sessions", timeout=5) as r:
                sessions = json.loads(r.read().decode())
            if sessions:
                sid = sessions[0]["session_id"]
                with urllib.request.urlopen(f"http://127.0.0.1:8017/api/studio/sessions/{sid}", timeout=5) as r:
                    full_sess = json.loads(r.read().decode())
                (PROOF_DIR / "studio-demo-summary.json").write_text(
                    json.dumps(full_sess, indent=2), encoding="utf-8"
                )

            # Transcode walkthrough .webm -> lightweight .mp4 and .gif
            mp4_out = OUT_DIR / "operator-ui-walkthrough.mp4"
            gif_out = OUT_DIR / "operator-ui-walkthrough.gif"
            if shutil.which("ffmpeg") and raw_webm.exists():
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(raw_webm),
                        "-c:v", "libx264", "-preset", "fast", "-crf", "26",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(mp4_out),
                    ],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(raw_webm),
                        "-vf", "fps=8,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
                        str(gif_out),
                    ],
                    check=True,
                    capture_output=True,
                )

        server.should_exit = True
        thread.join(timeout=3)

        print(json.dumps({
            "desktop_png": str(OUT_DIR / "operator-ui.png"),
            "mobile_png": str(OUT_DIR / "operator-ui-mobile.png"),
            "walkthrough_mp4": str(mp4_out),
            "walkthrough_mp4_bytes": mp4_out.stat().st_size if mp4_out.exists() else 0,
            "walkthrough_gif": str(gif_out),
            "walkthrough_gif_bytes": gif_out.stat().st_size if gif_out.exists() else 0,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
