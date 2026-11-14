"""Generate an accurate Figma-style design token & layout specification sheet for ClipOps Studio."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def _fonts():
    try:
        return {
            "h1": ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 26),
            "h2": ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16),
            "body": ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14),
            "mono": ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13),
            "xs": ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 11),
        }
    except OSError:
        d = ImageFont.load_default()
        return {"h1": d, "h2": d, "body": d, "mono": d, "xs": d}


def main() -> None:
    out = ROOT / "docs" / "images" / "clipops-figma-spec.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    f = _fonts()

    img = Image.new("RGB", (1400, 780), (7, 10, 16))
    d = ImageDraw.Draw(img)

    # Header
    d.text((40, 28), "ClipOps Studio — Precision NLE Design System & Layout Spec", fill=(230, 237, 247), font=f["h1"])
    d.text(
        (40, 64),
        "Design tokens & responsive proportions derived from apps/operator-ui/static/{index.html,styles.css} (anthropics/skills@frontend-design)",
        fill=(139, 155, 181),
        font=f["body"],
    )

    # Section 1: Color & Surface Tokens (Left column)
    d.rounded_rectangle([40, 105, 450, 470], radius=10, fill=(12, 17, 27), outline=(35, 48, 71), width=2)
    d.text((60, 124), "01  COLOR & SURFACE TOKENS", fill=(34, 211, 238), font=f["h2"])
    swatches = [
        ("--bg", "#070a10", (7, 10, 16), "Studio backdrop"),
        ("--chassis", "#0c111b", (12, 17, 27), "Topbar / timeline frame"),
        ("--panel", "#101724", (16, 23, 36), "Primary NLE rail & stage"),
        ("--well", "#151f30", (21, 31, 48), "Recessed control well"),
        ("--border", "#233047", (35, 48, 71), "1px structural hairline"),
        ("--cyan", "#22d3ee", (34, 211, 238), "Playhead & active word"),
        ("--green", "#10b981", (16, 185, 129), "Approved gate & 9:16 pass"),
        ("--amber", "#f59e0b", (245, 158, 11), "Hook curve & safe guide"),
        ("--red", "#ef4444", (239, 68, 68), "Reject gate & UI rail"),
    ]
    for i, (var, hx, rgb, role) in enumerate(swatches):
        y = 162 + i * 33
        d.rounded_rectangle([60, y, 84, y + 22], radius=4, fill=rgb, outline=(70, 90, 120), width=1)
        d.text((96, y + 4), f"{var:<10} {hx}", fill=(230, 237, 247), font=f["mono"])
        d.text((262, y + 4), role, fill=(139, 155, 181), font=f["xs"])

    # Section 2: 9:16 Safe-Zone Geometry inside 16:9 Source
    d.rounded_rectangle([40, 492, 450, 740], radius=10, fill=(12, 17, 27), outline=(35, 48, 71), width=2)
    d.text((60, 510), "02  9:16 CROP & SAFE MARGINS", fill=(245, 158, 11), font=f["h2"])
    # Mini 16:9 frame
    d.rectangle([62, 548, 302, 683], fill=(4, 6, 10), outline=(51, 71, 102), width=2)
    # 9:16 crop box centered: width = 135 * 9/16 = 76px -> x=144..220
    d.rectangle([144, 550, 220, 681], outline=(34, 211, 238), width=2)
    d.rectangle([147, 560, 217, 578], outline=(245, 158, 11), width=1)
    d.rectangle([206, 595, 218, 650], outline=(239, 68, 68), width=1)
    d.rectangle([147, 657, 203, 678], outline=(16, 185, 129), width=1)
    d.text((62, 696), "1280x720 -> 1080x1920 center crop", fill=(230, 237, 247), font=f["mono"])
    d.text((62, 714), "Wrapped hook <=26 chars/line, max 3 lines", fill=(139, 155, 181), font=f["xs"])
    d.text((314, 556), "TOP SAFE (13%)", fill=(252, 211, 77), font=f["xs"])
    d.text((314, 588), "UI RAIL (15% R)", fill=(252, 165, 165), font=f["xs"])
    d.text((314, 620), "CAPTION SAFE", fill=(110, 231, 183), font=f["xs"])
    d.text((314, 636), "(16% bottom)", fill=(139, 155, 181), font=f["xs"])

    # Section 3: Desktop NLE Grid Blueprint (Right wide panel)
    d.rounded_rectangle([476, 105, 1360, 740], radius=10, fill=(12, 17, 27), outline=(35, 48, 71), width=2)
    d.text((500, 124), "03  WORKSTATION GRID ANATOMY (1440x900 DESKTOP / <=1160px RESPONSIVE STACK)", fill=(16, 185, 129), font=f["h2"])

    # Topbar wireframe
    d.rounded_rectangle([500, 160, 1336, 204], radius=6, fill=(16, 23, 36), outline=(35, 48, 71), width=1)
    d.text((516, 174), "Topbar: Logo + Engines [FFmpeg, PySceneDetect, faster-whisper] + [Load 16:9 Podcast Example] [+ 24s Demo] [Open Local]", fill=(203, 213, 225), font=f["xs"])

    # 5-step stepper wireframe
    cols = [
        ("1. Probe", "0.95fr"),
        ("2. ASR Words", "1.2fr"),
        ("3. SceneDetect", "1.45fr"),
        ("4. Hook/Pacing", "1.15fr"),
        ("5. Render", "0.95fr"),
    ]
    sx = 500
    for idx, (title, fr) in enumerate(cols):
        w = 162 if idx != 2 else 172
        d.rounded_rectangle([sx, 214, sx + w, 254], radius=5, fill=(16, 23, 36), outline=(16, 185, 129) if idx < 4 else (35, 48, 71), width=1)
        d.text((sx + 10, 226), f"{title} ({fr})", fill=(226, 232, 240), font=f["xs"])
        sx += w + 6

    # 3-column workspace wireframe: 280px | 1fr | 370px
    # Col 1: 280px (scaled to 196px)
    d.rounded_rectangle([500, 266, 696, 714], radius=6, fill=(16, 23, 36), outline=(34, 211, 238), width=1)
    d.text((514, 280), "LEFT RAIL (280px)", fill=(34, 211, 238), font=f["mono"])
    d.text((514, 304), "• Project Bin (full-width)", fill=(203, 213, 225), font=f["xs"])
    d.text((514, 324), "• Media Probe Card", fill=(203, 213, 225), font=f["xs"])
    d.text((514, 344), "• Ranked Cuts List", fill=(203, 213, 225), font=f["xs"])
    for ci in range(3):
        cy = 376 + ci * 86
        d.rounded_rectangle([514, cy, 682, cy + 72], radius=5, fill=(21, 31, 48), outline=(34, 211, 238) if ci == 0 else (35, 48, 71), width=1)
        d.text((524, cy + 12), f"Cut #{ci + 1}  [score]", fill=(230, 237, 247), font=f["xs"])
        d.text((524, cy + 34), "APPROVED / WPM / hook", fill=(139, 155, 181), font=f["xs"])

    # Col 2: 1fr (scaled to 392px)
    d.rounded_rectangle([708, 266, 1088, 714], radius=6, fill=(16, 23, 36), outline=(56, 189, 248), width=1)
    d.text((722, 280), "CENTER STAGE (minmax(0, 1fr))", fill=(56, 189, 248), font=f["mono"])
    d.rounded_rectangle([722, 306, 1074, 468], radius=5, fill=(4, 6, 10), outline=(35, 48, 71), width=1)
    d.text((740, 320), "Program Monitor (16:9 Feed <-> 9:16 Cut)", fill=(226, 232, 240), font=f["xs"])
    d.text((740, 340), "Toggleable 9:16 Safe Guides + SMPTE HUD", fill=(139, 155, 181), font=f["xs"])
    d.rounded_rectangle([722, 476, 1074, 504], radius=4, fill=(21, 31, 48), outline=(35, 48, 71), width=1)
    d.text((734, 483), "Transport: Play [Space]  J / K / L  Mark In [  Out ]", fill=(203, 213, 225), font=f["xs"])
    # Multi-track timeline blueprint
    d.rounded_rectangle([722, 514, 1074, 624], radius=5, fill=(6, 9, 15), outline=(35, 48, 71), width=1)
    d.text((734, 524), "V1 SCENES   | S1 (0-9.2s) | S2 (9.2-21.8s) | S3", fill=(186, 230, 253), font=f["xs"])
    d.text((734, 554), "A1 WAVE/HOOK| 72-bin RMS bars + Amber hook curve", fill=(252, 211, 77), font=f["xs"])
    d.text((734, 584), "T1 CUT SPAN | [IN 9.233s ... OUT 21.767s]", fill=(110, 231, 183), font=f["xs"])
    d.line([886, 518, 886, 620], fill=(34, 211, 238), width=2)
    d.rounded_rectangle([722, 634, 1074, 700], radius=5, fill=(21, 31, 48), outline=(35, 48, 71), width=1)
    d.text((734, 646), "Cut Parameters + Gate CTAs:", fill=(226, 232, 240), font=f["xs"])
    d.text((734, 668), "[Approve A]  [Reject R]  [Dry-Run D]  [Render 9:16 MP4]", fill=(110, 231, 183), font=f["xs"])

    # Col 3: 370px (scaled to 236px)
    d.rounded_rectangle([1100, 266, 1336, 714], radius=6, fill=(16, 23, 36), outline=(16, 185, 129), width=1)
    d.text((1114, 280), "INSPECTOR (370px)", fill=(16, 185, 129), font=f["mono"])
    d.text((1114, 306), "Tabs:", fill=(226, 232, 240), font=f["xs"])
    d.text((1114, 328), "1. Transcript & Words", fill=(34, 211, 238), font=f["xs"])
    d.text((1122, 346), "Live word highlight + seek", fill=(139, 155, 181), font=f["xs"])
    d.text((1114, 376), "2. Hooks & Pacing", fill=(252, 211, 77), font=f["xs"])
    d.text((1122, 394), "7-dim scores, WPM, dead-air", fill=(139, 155, 181), font=f["xs"])
    d.text((1114, 424), "3. Filtergraph & Gate", fill=(110, 231, 183), font=f["xs"])
    d.text((1122, 442), "13 compliance checks +", fill=(139, 155, 181), font=f["xs"])
    d.text((1122, 458), "FFmpeg dry-run & SHA-256", fill=(139, 155, 181), font=f["xs"])
    d.rounded_rectangle([1114, 496, 1322, 700], radius=5, fill=(6, 9, 15), outline=(35, 48, 71), width=1)
    d.text((1126, 510), "Keyboard Shortcuts:", fill=(226, 232, 240), font=f["xs"])
    for ki, (k, desc) in enumerate([("Space", "Play / Pause"), ("J / K / L", "-1.5s / Pause / +1.5s"), ("A / R", "Approve / Reject cut"), ("D", "FFmpeg dry-run"), ("Click word", "Seek to word")]):
        ky = 538 + ki * 28
        d.text((1126, ky), k, fill=(34, 211, 238), font=f["xs"])
        d.text((1198, ky), desc, fill=(148, 163, 184), font=f["xs"])

    img.save(out, optimize=True)
    print(f"Saved {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
