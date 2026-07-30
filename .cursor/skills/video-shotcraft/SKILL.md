---
name: video-shotcraft
description: Use video-shotcraft Remotion shot recipes to improve ClipOps short-form hooks/captions/transitions on campaign footage. Also for product promo films when asked. Trigger when the user mentions video-shotcraft, shot cards, Ink Press, cinematic Remotion motion, or stronger ClipOps animation overlays.
---

# video-shotcraft × ClipOps

Upstream skill (full toolkit): install with:

```bash
./scripts/install_video_shotcraft.sh
```

That clones https://github.com/Vincentwei1021/video-shotcraft into
`~/.cursor/skills/video-shotcraft` (104 shot cards, demos, Ink Press template, SFX).

Then read **`$HOME/.cursor/skills/video-shotcraft/SKILL.md`** for production rules.

## ClipOps constraints (always)

ClipOps Operator Mode renders **authorized Content Rewards campaign footage** via
`templates/src/StyleOverlay.tsx` (9:16 Remotion overlays) — not stock B-roll.

| Do | Don't |
|----|-------|
| Borrow easing, typography entrance, karaoke timing, short holds from shot cards | Replace brand footage with Pexels / unrelated UI recreations |
| Improve hooks for dramatic / educational / commentary styles | Auto-post or invent CR-forbidden overlays |
| Copy useful bits from `assets/lib/` into `templates/` after adapting | Import the skill repo as a hard dependency of the API |
| Prefer 9:16 / Shorts timing (hold ≥0.5–1s after hook lands) | Port full 1920×1080 Ink Press promos as the CR default path |

## Recommended shot cards for ClipOps overlays

Browse: https://vincentwei1021.github.io/video-shotcraft/

| Style account | Shot ideas |
|---------------|------------|
| dramatic | `type-entrance-moves` (letter-drop), `cel-flash-stomp`, `speed-ramp-freeze` energy |
| educational | `marker-underline-title`, `gradient-word-sweep`, calm holds |
| commentary | `document-typewriter-reveal`, punchy captions, less decoration |

Implementation target: `templates/src/StyleOverlay.tsx` + `workers/video_rendering/render.py`.

## Product promo mode (optional)

If the user asks for a **product launch / marketing film** (not a CR clip package),
follow upstream Ink Press / pipeline modes in the cloned skill. Keep that work in a
separate Remotion composition — do not overwrite the ClipOps export pipeline.
