"""Game profiles: what a great clip looks like for a specific game.

A profile tunes the whole pipeline — chat vocabulary, spike thresholds, clip window,
moment categories (used for ranking and titles), and the post kit. `gta6` is the
launch-night profile; `default` works for any stream.

Knowledge behind these numbers lives in the Obsidian brain: vault/GTA6.md,
vault/GTA6Moments.md, vault/LiveClipping.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MomentCategory:
    name: str
    pattern: str  # case-insensitive regex matched against chat + transcript
    weight: float  # 0-1 virality prior used by ranking
    title: str  # post title template; {streamer} is filled in
    spoiler_risk: bool = False

    @property
    def regex(self) -> re.Pattern:
        return re.compile(r"(?i)\b(" + self.pattern + r")\b")


@dataclass(frozen=True)
class GameProfile:
    name: str
    display: str
    hype_terms: tuple[str, ...] = ()
    categories: tuple[MomentCategory, ...] = ()
    hashtags: tuple[str, ...] = ()
    # detector / clip tuning (None = keep ClipperConfig default)
    ratio_threshold: float | None = None
    z_threshold: float | None = None
    min_messages: int | None = None
    cooldown_seconds: float | None = None
    clip_seconds: float | None = None
    tail_seconds: float | None = None
    whisper_prompt: str | None = None  # vocabulary hint so Whisper spells game names right
    notes: tuple[str, ...] = field(default_factory=tuple)

    def category(self, name: str | None) -> MomentCategory | None:
        return next((c for c in self.categories if c.name == name), None)


GTA6 = GameProfile(
    name="gta6",
    display="GTA 6",
    hype_terms=(
        "wasted", "busted", "wanted", "5 stars", "five stars", "6 stars", "stars", "cops", "swat",
        "chase", "heist", "vice city", "leonida", "lucia", "jason", "gta", "gta6", "gta 6",
        "rockstar", "npc", "ragdoll", "glitch", "physics", "graphics", "realistic", "florida man",
        "gator", "alligator", "clip that", "clip it", "pause", "run it back", "first mission",
    ),
    categories=(
        MomentCategory(
            "chase", r"wanted|\d\s*stars?|five stars|six stars|cops?|police|swat|chase|helicopter|heli|getaway|pursuit",
            1.0, "{streamer}'s first police chase in GTA 6 went crazy",
        ),
        MomentCategory(
            "glitch", r"glitch\w*|bug(ged)?|physics|ragdoll|broken|clipping|t-?pose|flying car|launched|yeet\w*",
            1.0, "GTA 6 physics broke {streamer}",
        ),
        MomentCategory(
            "fail", r"wasted|busted|died|dead|rip|o7|fail\w*|he fell|she fell|crashed|missed",
            0.9, "{streamer} did NOT expect this in GTA 6",
        ),
        MomentCategory(
            "funny", r"lmao+|lmfao+|kekw|omegalul|lul+|icant|i can'?t|bro what|npc|florida man|gator|alligator",
            0.9, "{streamer} vs GTA 6 NPCs",
        ),
        MomentCategory(
            "graphics", r"graphics|realistic|looks real|photo ?real|next gen|ray ?tracing|4k|so clean|insane detail|water",
            0.7, "{streamer} can't believe GTA 6 graphics",
        ),
        MomentCategory(
            "world", r"vice city|leonida|map|beach|ocean drive|keys|easter egg|secret|hidden|found",
            0.7, "{streamer} explores Vice City in GTA 6",
        ),
        MomentCategory(
            "heist", r"heist|robbery|rob(bing)?|bank|store|safe|loot|money|cash",
            0.85, "{streamer}'s first GTA 6 robbery",
        ),
        MomentCategory(
            "story", r"lucia|jason|cutscene|ending|twist|betray\w*|spoiler\w*|plot|story|mission",
            0.5, "{streamer} reacts to GTA 6 (no spoilers)", spoiler_risk=True,
        ),
    ),
    hashtags=("#GTA6", "#GTAVI", "#ViceCity", "#Twitch", "#Gaming"),
    # Launch-night chats are enormous and already loud, so they can't jump 2.5x like a small chat;
    # the Poisson + MAD z-score tests still block noise.
    ratio_threshold=2.0,
    z_threshold=3.0,
    min_messages=15,
    cooldown_seconds=40.0,
    clip_seconds=30.0,
    tail_seconds=6.0,
    whisper_prompt="GTA 6, Grand Theft Auto VI, Vice City, Leonida, Lucia, Jason, Rockstar, wanted level, cops, heist.",
    notes=(
        "Reaction-led clips (facecam + gameplay) beat raw gameplay and are safer than cutscene rips.",
        "Never put story spoilers in titles or thumbnails during launch week.",
    ),
)

DEFAULT = GameProfile(
    name="default",
    display="stream",
    categories=(
        MomentCategory("funny", r"lmao+|lmfao+|kekw|omegalul|lul+|icant|bro what", 0.9, "{streamer} can't stop laughing"),
        MomentCategory("fail", r"rip|o7|fail\w*|died|dead", 0.8, "{streamer} did NOT expect this"),
        MomentCategory("hype", r"let'?s go+|pog\w*|w+|insane|holy", 0.8, "{streamer}'s craziest moment"),
    ),
    hashtags=("#Twitch", "#Clips"),
)

PROFILES = {p.name: p for p in (GTA6, DEFAULT)}


def get_profile(name: str | None) -> GameProfile:
    if not name:
        return DEFAULT
    try:
        return PROFILES[name.lower()]
    except KeyError as exc:
        raise ValueError(f"unknown profile {name!r}; choose from {sorted(PROFILES)}") from exc


def classify_moment(profile: GameProfile, *texts: str, counts: dict[str, int] | None = None) -> dict:
    """Pick the moment category from chat category counts and/or transcript text."""
    tally: dict[str, float] = dict(counts or {})
    blob = " ".join(t for t in texts if t)
    for c in profile.categories:
        hits = len(c.regex.findall(blob))
        if hits:
            tally[c.name] = tally.get(c.name, 0) + hits * 2  # streamer's own words count double
    if not tally:
        return {"category": None, "weight": 0.3, "spoiler_risk": False, "tally": {}}
    best = max(tally, key=lambda k: (tally[k], profile.category(k).weight if profile.category(k) else 0))
    cat = profile.category(best)
    return {
        "category": best,
        "weight": cat.weight if cat else 0.3,
        "spoiler_risk": bool(cat and cat.spoiler_risk),
        "tally": tally,
    }


def post_kit(profile: GameProfile, streamer: str, moment: dict, hook_line: str) -> dict:
    cat = profile.category(moment.get("category"))
    who = streamer or "Streamer"
    title = (cat.title if cat else f"{{streamer}}'s craziest {profile.display} moment").format(streamer=who)
    tags = list(profile.hashtags)
    handle = re.sub(r"[^A-Za-z0-9_]", "", who)
    if handle:
        tags.append(f"#{handle}")
    caption = f"{hook_line}\n\n{title}\n\n{' '.join(tags)}"
    if moment.get("spoiler_risk"):
        caption = "(no spoilers in title)\n" + caption
    return {"title": title, "hook": hook_line, "hashtags": tags, "caption": caption,
            "spoiler_risk": bool(moment.get("spoiler_risk"))}
