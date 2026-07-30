# video-shotcraft — animation assist for ClipOps

Source: [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)

Agent skill for cinematic Remotion motion (104 shot cards, demos, Ink Press template).
ClipOps uses it to **improve short-form overlays** on campaign footage — not to replace
Content Rewards cuts with stock product-promo films.

## Install (agents / local)

```bash
./scripts/install_video_shotcraft.sh
```

Clones into `~/.cursor/skills/video-shotcraft`. Project adapter:
`.cursor/skills/video-shotcraft/SKILL.md`.

Gallery (pick shot names): https://vincentwei1021.github.io/video-shotcraft/

## Where it plugs into ClipOps

| ClipOps piece | Role |
|---------------|------|
| `templates/src/StyleOverlay.tsx` | 9:16 hooks + karaoke captions (borrow easing / type entrance) |
| `templates/` Remotion service `:3100` | Renders overlays onto FFmpeg cuts |
| `workers/video_rendering/render.py` | Calls Remotion; FFmpeg fallback |

## Borrow vs leave upstream

| Borrow | Leave upstream / optional |
|--------|---------------------------|
| Timing, easing, hold-after-hook | Full Ink Press 1080p promo template as CR default |
| Typography entrance ideas for hooks | PageCam 2.5D product screenshot pipeline |
| Beat / rhythm sense for cuts | Auto music generation for CR exports |

## Example agent prompt

```text
Use video-shotcraft type-entrance-moves (letter-drop) to strengthen the
dramatic StyleOverlay hook on campaign footage. Keep 9:16 and karaoke captions.
Do not replace the source video.
```
