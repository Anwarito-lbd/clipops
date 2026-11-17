"""Edit renderer: frame-accurate beat-synced 9:16 cuts from video clips AND screenshots.

Every cut point is computed in whole frames from the music's beat grid, so cuts never drift.
Each slot is rendered from one shot (full layout) or two (split layout: top / bottom), then:
  slow-mo with frame blending (build/hold) - Ken Burns move on screenshots - zoom punch,
  shake and RGB split on hits - white flash on the drop - colour grade
and the joined edit gets glow, vignette, grain, the ASS text track and the music.
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
    "vice": "eq=contrast=1.18:saturation=1.28:gamma=0.97,colorbalance=rs=0.02:bs=0.04:rm=0.02:rh=0.05:gh=0.01:bh=-0.04",
    "gold": "eq=contrast=1.25:saturation=1.2:gamma=0.97,colorbalance=rm=0.08:gm=0.04:bm=-0.08:rh=0.06:bh=-0.06",
    "noir": "hue=s=0,eq=contrast=1.55:brightness=-0.03,curves=preset=strong_contrast",
    "teal": "eq=contrast=1.25:saturation=1.3,colorbalance=rs=-0.06:bs=0.12:rh=0.10:gh=0.02:bh=-0.06",
    "clean": "eq=contrast=1.12:saturation=1.15",
}


@dataclass
class Slot:
    start: float
    dur: float
    kind: str  # teaser | build | drop | hit | flash | hold | end
    speed: float = 1.0
    frames: int = 0


@dataclass
class TextEvent:
    start: float  # seconds from edit start
    end: float
    text: str
    style: str = "Top"  # Top | Glow | Foot | Label | Mid
    pop: bool = False


@dataclass
class EditSpec:
    style: str = "vice"
    pre_seconds: float = 6.5
    post_seconds: float = 12.0
    seed: int = 1
    font: str = "DejaVu Sans"
    teaser: bool = True  # 1-beat flash-forward of the drop shot as the opening hook
    layout: str = "full"  # full | split
    labels: tuple[str, str] = ("TRAILER", "GAMEPLAY")
    texts: list[TextEvent] = field(default_factory=list)


# ------------------------------------------------------------------------------------------- plan

def plan_slots(m: MusicInfo, spec: EditSpec, *, end_slot: bool = False) -> tuple[float, float, list[Slot]]:
    beats = [b for b in m.beats if b >= 0]
    if not beats:
        raise ValueError("no beats found in the music")
    b = m.beat
    build_step = 2 if b >= 0.36 else 4
    target = max(beats[0], m.drop - spec.pre_seconds)
    start = min((x for x in beats if x <= m.drop), key=lambda x: abs(x - target), default=beats[0])
    end_target = min(m.duration - 0.3, m.drop + spec.post_seconds)
    grid = [x for x in beats if start <= x <= end_target]
    if grid[-1] < end_target - b * 0.5:
        grid.append(min(end_target, grid[-1] + b))
    slots: list[Slot] = []
    i = 0
    if spec.teaser and len(grid) > 2 and grid[1] < m.drop:
        slots.append(Slot(grid[0], grid[1] - grid[0], "teaser"))
        i = 1
    while i < len(grid) - 1:
        t = grid[i]
        if t < m.drop - 1e-3:
            j = min(i + build_step, len(grid) - 1)
            while grid[j] > m.drop + 1e-3:
                j -= 1
            j = max(j, i + 1)
            slots.append(Slot(t, grid[j] - t, "build", 0.5))
            i = j
            continue
        n_post = sum(1 for s in slots if s.kind not in ("build", "teaser"))
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
    if end_slot and len(slots) > 3:
        last, prev = slots.pop(), slots.pop()
        slots.append(Slot(prev.start, last.start + last.dur - prev.start, "end"))
    end = slots[-1].start + slots[-1].dur
    _assign_frames(slots, start)
    return start, end, slots


def _assign_frames(slots: list[Slot], start: float) -> None:
    for s in slots:
        f0 = round((s.start - start) * FPS)
        f1 = round((s.start + s.dur - start) * FPS)
        s.frames = max(1, f1 - f0)


def pick_shots(slots: list[Slot], pool: list[Shot], seed: int, *, avoid: set | None = None) -> list[tuple[Shot, float]]:
    """One shot per slot: calm/colourful for build & holds, most intense for hits; spread usage."""
    rng = random.Random(seed)
    calm = sorted((s for s in pool if s.score("calm") > 0), key=lambda s: -s.score("calm"))
    intense = sorted((s for s in pool if s.score("intense") > 0), key=lambda s: -s.score("intense"))
    hero = sorted((s for s in pool if s.score("hero") > 0), key=lambda s: -s.score("hero"))[:3]
    used: dict[tuple[str, float], int] = {}
    if avoid:
        for k in avoid:
            used[k] = 1
    out: list[tuple[Shot, float]] = []
    drop_pick = None
    for slot in slots:
        need = slot.frames / FPS * slot.speed
        ranked = calm if slot.kind in ("build", "hold", "end") else (hero if slot.kind == "drop" else intense)
        fits = [s for s in ranked if s.kind == "image" or s.length >= need] or ranked[:5]
        top = fits[: max(6, len(fits) // 3)]
        least = min(used.get((s.path, s.start), 0) for s in top)
        choice = rng.choice([s for s in top if used.get((s.path, s.start), 0) == least])
        used[(choice.path, choice.start)] = used.get((choice.path, choice.start), 0) + 1
        t = choice.start + rng.uniform(0, max(0.0, choice.length - need)) if choice.kind != "image" else 0.0
        out.append((choice, t))
        if slot.kind == "drop":
            drop_pick = (choice, t)
    if drop_pick and slots and slots[0].kind == "teaser":
        out[0] = drop_pick  # the hook flashes forward to the drop shot
    return out


# ----------------------------------------------------------------------------------------- render

def _shot_chain(idx: int, shot: Shot, slot: Slot, w: int, h: int, rng: random.Random) -> str:
    """Filter chain for input `idx` -> exactly w x h at FPS, with motion appropriate to the slot."""
    n = slot.frames
    p = []
    if shot.kind == "image":
        # Ken Burns: crop a w:h window from the 4K still, slow zoom + drift; punch on hits
        p.append(f"scale=-2:{int(h * 1.35)}:flags=lanczos")
        p.append(f"crop='min(iw,ih*{w}/{h})':ih:'(iw-ow)*{rng.uniform(0.25, 0.75):.2f}':0")
        p.append(f"scale={int(w * 1.25)}:{int(h * 1.25)}")
        zoom = (f"1.0+0.10*on/{n}" if slot.kind in ("build", "hold", "end", "teaser")
                else f"1.06+0.20*exp(-on/{FPS}*9)")
        dx = rng.choice([-1, 1]) * 0.06
        p.append(f"zoompan=z='{zoom}':x='(iw-iw/zoom)/2+iw*{dx}*on/{n}':y='(ih-ih/zoom)/2':d={n}:s={w}x{h}:fps={FPS}")
    else:
        top, bot = getattr(shot, "bars", (0.0, 0.0)) or (0.0, 0.0)
        if top or bot:  # remove baked-in cinematic letterbox before reframing to 9:16
            p.append(f"crop=iw:'trunc(ih*{1 - top - bot:.4f}/2)*2':0:'trunc(ih*{top:.4f}/2)*2'")
        if slot.speed != 1.0:
            p.append(f"setpts={1 / slot.speed:.4f}*PTS,minterpolate=fps={FPS}:mi_mode=blend")
        p.append(f"fps={FPS}")
        if slot.kind == "end":  # logos/end cards are wide: show the whole frame over a blurred fill
            src = f"[{idx}:v]" + ",".join(p)
            return (f"{src},split=2[eb{idx}][ef{idx}];"
                    f"[eb{idx}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=40,"
                    f"eq=brightness=-0.12[ebb{idx}];[ef{idx}]scale={w}:-2[eff{idx}];"
                    f"[ebb{idx}][eff{idx}]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[s{idx}]")
        if slot.kind in ("build", "hold"):
            direction = rng.choice([-1, 1])
            p.append(f"crop='min(iw,ih*{w}/{h})':ih:'(iw-ow)/2+{direction}*(iw-ow)/2*0.5*(2*n/{n}-1)':0")
        else:
            p.append(f"crop='min(iw,ih*{w}/{h})':ih:'(iw-ow)/2*(1+{rng.uniform(-0.2, 0.2):.2f})':0")
        p.append(f"scale={w}:{h}:flags=lanczos")
        if slot.kind in ("drop", "flash", "teaser"):
            p.append(f"zoompan=z='1+0.22*exp(-on/{FPS}*9)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={FPS}")
    p.append("setsar=1,format=yuv420p")
    return f"[{idx}:v]" + ",".join(p) + f"[s{idx}]"


def _render_slot(slot: Slot, shots: list[tuple[Shot, float]], spec: EditSpec, out: Path, rng: random.Random) -> None:
    n = slot.frames
    inputs, chains = [], []
    split = len(shots) == 2
    w, h = (W, H // 2) if split else (W, H)
    for k, (shot, t) in enumerate(shots):
        if shot.kind == "image":
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.2:.3f}", "-i", shot.path]
        else:
            inputs += ["-ss", f"{t:.3f}", "-t", f"{n / FPS * slot.speed + 0.3:.3f}", "-i", shot.path]
        chains.append(_shot_chain(k, shot, slot, w, h, rng))
    graph = ";".join(chains) + ";"
    graph += "[s0][s1]vstack=inputs=2,drawbox=x=0:y=954:w=1080:h=12:color=white@0.95:t=fill[c];" if split else "[s0]null[c];"
    fx = []
    if slot.kind in ("drop", "flash"):
        # shake inside the image (zoom 7 % first) so no black edges ever show
        fx.append(f"scale={W + 76}:{H + 134},crop={W}:{H}:x='38+34*sin(n*1.77)*exp(-n/{FPS}*3)':y='67+60*cos(n*1.57)*exp(-n/{FPS}*3)'")
        fx.append("rgbashift=rh=8:bh=-8:rv=2:bv=-2")
    fx.append(GRADES.get(spec.style, GRADES["vice"]))
    if slot.kind in ("drop", "flash", "teaser"):
        fx.append("fade=t=in:st=0:d=0.14:color=white")
    if slot.kind == "end":
        fx.append(f"fade=t=out:st={max(0.0, n / FPS - 0.6):.3f}:d=0.6")
    graph += "[c]" + ",".join(fx) + "[v]"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-an",
           "-frames:v", str(n), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", str(out)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m_, s = divmod(r, 60)
    return f"{int(h)}:{int(m_):02d}:{s:05.2f}"


def build_ass(spec: EditSpec, events: list[TextEvent]) -> str:
    f = spec.font
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Glow,{f},190,&H00FFFFFF,&H00FFFFFF,&H00C040FF,&H00000000,-1,0,0,0,100,100,20,0,1,9,0,5,30,30,0,1\n"
        f"Style: Mid,{f},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,8,0,1,6,2,5,40,40,0,1\n"
        f"Style: Top,{f},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,8,0,1,7,3,8,40,40,330,1\n"
        f"Style: Foot,{f},58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,8,0,1,3,1,2,40,40,300,1\n"
        f"Style: Label,{f},40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,8,0,3,10,0,7,40,40,40,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    pop = r"{\fscx55\fscy55\t(0,90,\fscx112\fscy112)\t(90,200,\fscx100\fscy100)}"
    lines = []
    for e in events:
        txt = e.text.replace("\n", r"\N")
        lines.append(f"Dialogue: 1,{_ass_time(e.start)},{_ass_time(e.end)},{e.style},,0,0,0,,"
                     f"{pop if e.pop else ''}{txt}")
    return head + "\n".join(lines) + "\n"


def render(m: MusicInfo, start: float, end: float, slots: list[Slot], picks: list[list[tuple[Shot, float]]],
           out_path: str | Path, spec: EditSpec, *, log=print, keep_audio_dir: bool = False) -> dict:
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(spec.seed * 7919)
    work = Path(tempfile.mkdtemp(prefix="edit_", dir=str(out_path.parent)))
    parts = []
    for k, (slot, shots) in enumerate(zip(slots, picks)):
        part = work / f"p{k:03d}.mp4"
        _render_slot(slot, shots, spec, part, rng)
        parts.append(part)
    (work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-c", "copy", "joined.mp4"], check=True, capture_output=True, text=True, cwd=work)
    events = list(spec.texts)
    if spec.layout == "split":
        events += [TextEvent(0, end - start, spec.labels[0], "Label"),
                   TextEvent(0, end - start, r"{\an1\pos(40,1010)}" + spec.labels[1], "Label")]
    (work / "text.ass").write_text(build_ass(spec, events), encoding="utf-8")
    total_frames = sum(s.frames for s in slots)
    dur = total_frames / FPS
    # glow only on highlights (curves crush the blurred layer's shadows) so blacks stay deep
    vf = ("split=2[a][b];[b]gblur=sigma=20,curves=all='0/0 0.55/0.08 1/0.85'[g];"
          "[a][g]blend=all_mode=screen:all_opacity=0.32,eq=contrast=1.05,"
          "vignette=PI/4.4,noise=alls=4:allf=t,format=yuv420p,subtitles=filename=text.ass")
    af = (f"atrim=start={start:.4f}:duration={dur:.4f},asetpts=PTS-STARTPTS,"
          f"afade=t=out:st={max(0, dur - 0.8):.3f}:d=0.8,loudnorm=I=-11:TP=-1.0:LRA=7")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", "joined.mp4", "-i", str(Path(m.path).resolve()),
                    "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]",
                    "-frames:v", str(total_frames), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-maxrate", "14M", "-bufsize", "28M", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)],
                   check=True, capture_output=True, text=True, cwd=work)
    silent = out_path.with_name(out_path.stem + "_NO_AUDIO.mp4")  # for adding the sound in the TikTok app
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(out_path), "-c:v", "copy", "-an", str(silent)],
                   check=True, capture_output=True, text=True)
    for p in work.iterdir():
        p.unlink()
    work.rmdir()
    log(f"rendered {out_path.name}: {dur:.2f}s, {len(slots)} cuts, drop at {m.drop - start:.2f}s")
    return {"path": str(out_path), "silent": str(silent), "duration": round(dur, 2), "cuts": len(slots),
            "drop_at": round(m.drop - start, 3), "start_in_song": round(start, 3), "tempo": round(m.tempo, 1),
            "shots": [[(Path(s.path).name, round(t, 2)) for s, t in pk] for pk in picks]}
