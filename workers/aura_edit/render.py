"""Aura edit renderer: beat-synced 9:16 cut with slow-mo build-up, flash + zoom-punch drop,
RGB split, shake, glow, grade, grain and big pop-in text.

Timeline (all cut points land on beats):
  build  : 2-beat slots, 0.5x blended slow-mo, slow pan, cinematic shots
  drop   : white flash + zoom punch + shake + RGB split on the first hit
  hits   : 1-beat cuts of the most intense shots, every 4th hit flashes
  holds  : every 6th slot is a 2-beat 0.6x hold to let the edit breathe
  end    : optional logo/end shot with fade
"""

from __future__ import annotations

import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import MusicInfo, Shot

FPS = 30
W, H = 1080, 1920

GRADES = {
    "vice": "eq=contrast=1.22:saturation=1.45:gamma=0.95,colorbalance=rs=0.10:bs=0.14:rh=0.06:bh=0.04",
    "gold": "eq=contrast=1.25:saturation=1.2:gamma=0.97,colorbalance=rm=0.08:gm=0.04:bm=-0.08:rh=0.06:bh=-0.06",
    "noir": "hue=s=0,eq=contrast=1.55:brightness=-0.03,curves=preset=strong_contrast",
    "teal": "eq=contrast=1.25:saturation=1.3,colorbalance=rs=-0.06:bs=0.12:rh=0.10:gh=0.02:bh=-0.06",
}


@dataclass
class Slot:
    start: float
    dur: float
    kind: str  # build | drop | hit | flash | hold | end
    speed: float = 1.0


@dataclass
class EditSpec:
    style: str = "vice"
    texts: dict = field(default_factory=lambda: {"build": "VICE CITY", "drop": "AURA", "end": "GTA VI · 11.19"})
    pre_seconds: float = 6.5
    post_seconds: float = 12.0
    seed: int = 1
    font: str = "DejaVu Sans"
    end_shot: Shot | None = None  # e.g. the GTA VI logo moment


def plan_slots(m: MusicInfo, spec: EditSpec) -> tuple[float, float, list[Slot]]:
    beats = [b for b in m.beats if b >= 0]
    if not beats:
        raise ValueError("no beats found in the music")
    b = m.beat
    build_step = 2 if b >= 0.36 else 4
    start = max(beats[0], m.drop - spec.pre_seconds)
    start = min((x for x in beats if x <= m.drop), key=lambda x: abs(x - start), default=beats[0])
    end_target = min(m.duration - 0.3, m.drop + spec.post_seconds)
    grid = [x for x in beats if start <= x <= end_target]
    if grid[-1] < end_target - b * 0.5:
        grid.append(min(end_target, grid[-1] + b))
    slots: list[Slot] = []
    i = 0
    while i < len(grid) - 1:
        t = grid[i]
        if t < m.drop - 1e-3:
            j = min(i + build_step, len(grid) - 1)
            while grid[j] > m.drop + 1e-3:  # never let a build slot cross the drop
                j -= 1
            if j == i:
                j = i + 1
            slots.append(Slot(t, grid[j] - t, "build", 0.5))
            i = j
            continue
        n_post = sum(1 for s in slots if s.kind != "build")
        if n_post == 0:
            kind, step, speed = "drop", 1, 1.0
        elif n_post % 6 == 5:
            kind, step, speed = "hold", 2, 0.6
        elif n_post % 4 == 0:
            kind, step, speed = "flash", 1, 1.0
        else:
            kind, step, speed = "hit", 1, 1.0
        j = min(i + step, len(grid) - 1)
        slots.append(Slot(t, grid[j] - t, kind, speed))
        i = j
    if spec.end_shot is not None and len(slots) > 2:
        last = slots.pop()
        prev = slots.pop()
        slots.append(Slot(prev.start, last.start + last.dur - prev.start, "end", 1.0))
    return start, slots[-1].start + slots[-1].dur, slots


def assign_shots(slots: list[Slot], pool: list[Shot], spec: EditSpec) -> list[tuple[Slot, Shot, float]]:
    rng = random.Random(spec.seed)
    calm = sorted((s for s in pool if s.score("calm") > 0), key=lambda s: -s.score("calm"))
    intense = sorted((s for s in pool if s.score("intense") > 0), key=lambda s: -s.score("intense"))
    used: dict[tuple[str, float], int] = {}
    out = []
    for slot in slots:
        if slot.kind == "end" and spec.end_shot is not None:
            out.append((slot, spec.end_shot, spec.end_shot.start))
            continue
        need = slot.dur * slot.speed
        ranked = calm if slot.kind in ("build", "hold") else intense
        fits = [s for s in ranked if s.length >= need]
        if not fits:
            fits = sorted(pool, key=lambda s: -s.length)[:5]
        top = fits[: max(6, len(fits) // 3)]
        top.sort(key=lambda s: used.get((s.path, s.start), 0))  # least-used first
        least = used.get((top[0].path, top[0].start), 0)
        choice = rng.choice([s for s in top if used.get((s.path, s.start), 0) == least])
        used[(choice.path, choice.start)] = used.get((choice.path, choice.start), 0) + 1
        slack = max(0.0, choice.length - need)
        out.append((slot, choice, choice.start + rng.uniform(0, slack)))
    return out


def _slot_filter(slot: Slot, shot: Shot, spec: EditSpec, rng: random.Random) -> str:
    parts = []
    if shot.kind == "image":
        parts.append("loop=loop=-1:size=1:start=0,fps=30")
    if slot.speed != 1.0 and shot.kind != "image":
        parts.append(f"setpts={1 / slot.speed:.4f}*PTS")
        parts.append(f"minterpolate=fps={FPS}:mi_mode=blend")
    parts.append(f"fps={FPS}")
    # 9:16 crop from landscape; build/hold slots pan slowly across the frame
    if slot.kind == "end":
        parts.append("crop='min(iw,ih*9/16)':ih:'(iw-ow)/2':0")
    elif slot.kind in ("build", "hold"):
        direction = rng.choice([-1, 1])
        parts.append(f"crop='min(iw,ih*9/16)':ih:'(iw-ow)/2+{direction}*(iw-ow)/2*0.55*(2*t/{max(slot.dur, 0.1):.3f}-1)':0")
    else:
        offset = rng.uniform(-0.25, 0.25)
        parts.append(f"crop='min(iw,ih*9/16)':ih:'(iw-ow)/2*(1+{offset:.3f})':0")
    shaky = slot.kind in ("drop", "flash")
    big_w, big_h = (1150, 2044) if shaky else (W, H)
    parts.append(f"scale={big_w}:{big_h}:flags=lanczos,setsar=1")
    if slot.kind in ("drop", "flash"):
        parts.append(f"zoompan=z='1+0.22*exp(-in_time*9)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={big_w}x{big_h}:fps={FPS}")
    if shaky:
        parts.append(f"crop={W}:{H}:x='{(big_w - W) // 2}+{(big_w - W) // 2 - 4}*sin(t*53)*exp(-t*3)':"
                     f"y='{(big_h - H) // 2}+{(big_h - H) // 2 - 4}*cos(t*47)*exp(-t*3)'")
        parts.append("rgbashift=rh=8:bh=-8:rv=2:bv=-2")
    parts.append(GRADES.get(spec.style, GRADES["vice"]))
    if slot.kind in ("drop", "flash"):
        parts.append("fade=t=in:st=0:d=0.14:color=white")
    if slot.kind == "end":
        parts.append(f"fade=t=out:st={max(0.0, slot.dur - 0.6):.3f}:d=0.6")
    return ",".join(parts)


def _post_filter() -> str:
    # glow (screen-blended blur), vignette, film grain — applied once on the joined edit
    return ("split=2[a][b];[b]gblur=sigma=18[g];[a][g]blend=all_mode=screen:all_opacity=0.28,"
            "vignette=PI/4.5,noise=alls=9:allf=t,format=yuv420p")


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m_, s = divmod(r, 60)
    return f"{int(h)}:{int(m_):02d}:{s:05.2f}"


def build_text(spec: EditSpec, m: MusicInfo, start: float, end: float) -> str:
    drop = m.drop - start
    b = m.beat
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Glow,{spec.font},120,&H00FFFFFF,&H00FFFFFF,&H00FF66FF,&H00000000,-1,0,0,0,100,100,18,0,1,6,0,5,40,40,0,1\n"
        f"Style: Top,{spec.font},64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,14,0,1,4,2,8,40,40,260,1\n"
        f"Style: Foot,{spec.font},46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,10,0,1,3,1,2,40,40,300,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ev = []
    t = spec.texts
    if t.get("build") and drop > 1:
        ev.append(f"Dialogue: 0,{_ass_time(0.3)},{_ass_time(drop - b * 0.6)},Top,,0,0,0,,{{\\fad(400,150)}}{t['build']}")
    if t.get("drop"):
        pop = r"{\fscx60\fscy60\t(0,90,\fscx112\fscy112)\t(90,200,\fscx100\fscy100)\blur2}"
        ev.append(f"Dialogue: 1,{_ass_time(drop)},{_ass_time(drop + b * 2)},Glow,,0,0,0,,{pop}{t['drop']}")
    if t.get("end"):
        ev.append(f"Dialogue: 0,{_ass_time(max(drop + b * 2, end - start - 2.2))},{_ass_time(end - start)},Foot,,0,0,0,,"
                  f"{{\\fad(300,300)}}{t['end']}")
    return head + "\n".join(ev) + "\n"


def render_edit(m: MusicInfo, pool: list[Shot], out_path: str | Path, spec: EditSpec, *, log=print) -> dict:
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start, end, slots = plan_slots(m, spec)
    plan = assign_shots(slots, pool, spec)
    rng = random.Random(spec.seed * 7919)
    work = Path(tempfile.mkdtemp(prefix="aura_", dir=str(out_path.parent)))
    parts = []
    for k, (slot, shot, src_t) in enumerate(plan):
        part = work / f"p{k:03d}.mp4"
        vf = _slot_filter(slot, shot, spec, rng)
        src_dur = slot.dur * slot.speed + 0.2
        inp = ["-i", shot.path] if shot.kind == "image" else ["-ss", f"{src_t:.3f}", "-t", f"{src_dur:.3f}", "-i", shot.path]
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", *inp, "-vf", vf, "-an", "-t", f"{slot.dur:.4f}",
               "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(part)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        parts.append(part)
    (work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = work / "joined.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-c", "copy", joined.name], check=True, capture_output=True, text=True, cwd=work)
    (work / "text.ass").write_text(build_text(spec, m, start, end), encoding="utf-8")
    dur = end - start
    vf = f"{_post_filter()},subtitles=filename=text.ass"
    af = f"atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0, dur - 1.0):.3f}:d=1.0,loudnorm=I=-11:TP=-1.0:LRA=7"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", joined.name, "-i", str(Path(m.path).resolve()),
                    "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]",
                    "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)],
                   check=True, capture_output=True, text=True, cwd=work)
    for p in work.iterdir():
        p.unlink()
    work.rmdir()
    log(f"rendered {out_path.name}: {dur:.1f}s, {len(slots)} cuts, drop at {m.drop - start:.2f}s, style {spec.style}")
    return {"path": str(out_path), "duration": round(dur, 2), "cuts": len(slots), "drop_at": round(m.drop - start, 2),
            "tempo": round(m.tempo, 1), "style": spec.style,
            "shots": [{"src": Path(s.path).name, "t": round(t, 2), "kind": sl.kind} for sl, s, t in plan]}
