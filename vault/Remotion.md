---
tags:
  - architecture
---

# Remotion Caption Compositing

Upstream: [[Editing]], [[Hooks]] · Related: [[Models]], [[OperatorUI]]

Implemented in `templates/server.js`, `templates/src/Root.tsx`, `templates/src/StyleOverlay.tsx`, and per-style compositions under `templates/dramatic/`, `templates/educational/`, and `templates/commentary/`.

## Architecture

1. **FFmpeg Base Cut First**: `workers/video_rendering/render.py` cuts, crops to `1080×1920`, applies style zoom, and normalizes loudness (`loudnorm`) into `base_cut.mp4`.
2. **Optional Remotion Pass (`_try_remotion_overlay`)**: If `REMOTION_URL` is configured (default `http://127.0.0.1:3100`), the worker sends `POST /render` with `{ style, hookText, caption, inputVideo, outputPath }`.
3. **Local Video Proxy**: Because Remotion's `<OffthreadVideo>` requires `http(s)://` URLs, `templates/server.js` exposes `GET /local-file?path=...` (extension-allowlisted to `.mp4/.webm/.mov/.mkv/.m4v`) to stream `base_cut.mp4` into the headless Chromium renderer.
4. **React Compositions**: Three registered compositions (`Dramatic`, `Educational`, `Commentary`) render animated kinetic hook typography and caption safe-zones at `30 fps`, `1080×1920`.
5. **Fail-Safe Fallback**: If Remotion is offline or returns an empty file, [[Editing]] keeps the FFmpeg `drawtext` base cut cleanly so the local workstation never blocks on Node/Chromium.

See [[Config]] for `REMOTION_URL` and [[Home]] for the full pipeline map.
