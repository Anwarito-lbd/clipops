"""Original edit concepts built on the beat-synced renderer.

split  "Rockstar didn't lie": trailer shot on top, its closest real-gameplay match below
       (auto-matched by layout + colour), swapping on every beat; hook -> drop reveal -> comment bait.
aura   mixed short video clips + official screenshots (Ken Burns), slow-mo build, flash drop.
"""

from __future__ import annotations

from .analysis import MusicInfo, Shot, match_pairs
from .render import EditSpec, TextEvent, pick_shots, plan_slots, render


def _centered(shot: Shot, need: float) -> float:
    if shot.kind == "image":
        return 0.0
    mid = (shot.start + shot.end) / 2
    return max(shot.start, min(shot.end - need, mid - need / 2))


def make_split(m: MusicInfo, trailer: list[Shot], gameplay: list[Shot], out: str, spec: EditSpec | None = None,
               *, hook: str = "THEY SAID THE TRAILER\nWAS REAL GAMEPLAY", reveal: str = "THEY DIDN'T LIE",
               outro: str = "TOP OR BOTTOM?", log=print) -> dict:
    spec = spec or EditSpec(style="clean", layout="split")
    spec.layout = "split"
    start, end, slots = plan_slots(m, spec)
    pairs = match_pairs(trailer, gameplay, len(slots) + 4)
    if len(pairs) < len(slots):
        raise ValueError(f"only {len(pairs)} matched pairs for {len(slots)} cuts")
    # best matches go where people look hardest: the drop (and the teaser hook), then the hits
    order = sorted(range(len(slots)), key=lambda i: (slots[i].kind not in ("drop",), slots[i].kind == "build", i))
    picks: list = [None] * len(slots)
    for rank, i in enumerate(order):
        a, b, _ = pairs[rank]
        need = slots[i].frames / 30 * slots[i].speed
        picks[i] = [(a, _centered(a, need)), (b, _centered(b, need))]
    if slots[0].kind == "teaser":
        drop_i = next(i for i, s in enumerate(slots) if s.kind == "drop")
        picks[0] = picks[drop_i]
    drop = m.drop - start
    b = m.beat
    total = end - start
    spec.texts = [
        TextEvent(slots[0].frames / 30, drop - b * 0.3, hook, "Mid"),
        TextEvent(drop, drop + b * 3, reveal, "Glow", pop=True),
        TextEvent(max(drop + b * 3, total - 2.4), total, outro, "Mid", pop=True),
    ]
    res = render(m, start, end, slots, picks, out, spec, log=log)
    res["match_distances"] = [round(d, 4) for _, _, d in pairs[: len(slots)]]
    return res


def make_aura(m: MusicInfo, clips: list[Shot], stills: list[Shot], out: str, spec: EditSpec | None = None,
              *, end_shot: Shot | None = None, build: str = "WELCOME TO VICE CITY", drop_text: str = "AURA",
              outro: str = "GTA VI · 11.19", still_every: int = 3, log=print) -> dict:
    """Video clips for the hits, screenshots woven in every `still_every` slots and on holds."""
    spec = spec or EditSpec(style="vice")
    start, end, slots = plan_slots(m, spec, end_slot=end_shot is not None)
    clip_picks = pick_shots(slots, clips, spec.seed)
    still_picks = pick_shots(slots, stills, spec.seed + 1) if stills else clip_picks
    picks = []
    for i, s in enumerate(slots):
        if s.kind == "end" and end_shot is not None:
            picks.append([(end_shot, end_shot.start)])
        elif stills and (s.kind == "hold" or (s.kind in ("build", "hit") and i % still_every == 1)):
            picks.append([still_picks[i]])
        else:
            picks.append([clip_picks[i]])
    if slots[0].kind == "teaser":
        drop_i = next(i for i, s in enumerate(slots) if s.kind == "drop")
        picks[0] = picks[drop_i]
    drop, b, total = m.drop - start, m.beat, end - start
    spec.texts = [
        TextEvent(slots[0].frames / 30, drop - b * 0.3, build, "Top"),
        TextEvent(drop, drop + b * 2, drop_text, "Glow", pop=True),
        TextEvent(max(drop + b * 2, total - 2.2), total, outro, "Foot"),
    ]
    return render(m, start, end, slots, picks, out, spec, log=log)


def script_events(script: list[tuple[str, str, float]], beat: float, t0: float = 0.0, *, pop: bool = True) -> list[TextEvent]:
    """Lay (text, style, beats) entries back to back from t0; empty text = a silent gap (tension)."""
    out, t = [], t0
    for text, style, beats in script:
        if text:
            out.append(TextEvent(t, t + beats * beat - 0.02, text, style, pop=pop))
        t += beats * beat
    return out


def make_story(m: MusicInfo, clips: list[Shot], stills: list[Shot], out: str, spec: EditSpec | None = None, *,
               build_script: list[tuple[str, str, float]] | None = None,
               drop_script: list[tuple[str, str, float]] | None = None,
               outro: str = "GTA VI  ·  11.19", still_every: int = 3, loop: bool = True, log=print) -> dict:
    """Cold-open stakes text from frame 1, word-per-beat story through the build, reveal on the drop,
    beat-cut payoff mixing clips + stills, and a last cut that flows back into the first frame (loop)."""
    spec = spec or EditSpec(style="cinema")
    start, end, slots = plan_slots(m, spec)
    clip_picks = pick_shots(slots, clips, spec.seed)
    still_picks = pick_shots(slots, stills, spec.seed + 1) if stills else clip_picks
    picks = []
    for i, s in enumerate(slots):
        if stills and (s.kind == "hold" or (s.kind in ("build", "hit") and i % still_every == 1)):
            picks.append([still_picks[i]])
        else:
            picks.append([clip_picks[i]])
    drop_i = next(i for i, s in enumerate(slots) if s.kind == "drop")
    if slots[0].kind == "teaser":
        picks[0] = picks[drop_i]
    if loop and slots[0].kind == "teaser" and picks[0][0][0].kind != "image":
        shot, t_first = picks[0][0]
        need = slots[-1].frames / 30
        picks[-1] = [(shot, max(shot.start, t_first - need))]  # ends exactly where the video starts
        slots[-1].kind, slots[-1].speed = "hit", 1.0
    b = m.beat
    drop = m.drop - start
    total = end - start
    build_script = build_script or [("13 YEARS.", "Big", 3), ("we waited", "Accent", 2),
                                    ("THIRTEEN", "Big", 1), ("YEARS", "Big", 1), ("for this.", "Accent", 3)]
    drop_script = drop_script or [("finally.", "Accent", 2), ("", "", 4), ("VICE", "Big", 1), ("CITY", "Big", 1)]
    used = sum(x[2] for x in build_script) * b
    if used > drop - b * 0.5:  # keep the last build beat silent for the tape-stop
        raise ValueError(f"build script is {used:.2f}s but only {drop - b:.2f}s before the drop")
    spec.texts = script_events(build_script, b, 0.0) + script_events(drop_script, b, drop)
    spec.texts.append(TextEvent(max(drop + b * 8, total - 2.4), total, outro, "Small"))
    return render(m, start, end, slots, picks, out, spec, log=log)
