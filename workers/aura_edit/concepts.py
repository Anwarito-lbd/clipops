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
