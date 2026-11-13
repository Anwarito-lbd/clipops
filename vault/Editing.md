---
tags:
  - pipeline
---

# Editing & FFmpeg Filtergraphs

Upstream: [[Hooks]], [[RetentionPacing]] · Optional Pass: [[Remotion]] · Downstream: [[Export]], [[OperatorUI]]

Implemented in `workers/video_rendering/render.py` (`build_filtergraph` and `render_account_package`).

## Filtergraph Pipeline (`build_filtergraph`)

Every vertical `9:16` cut is built deterministically before execution so [[OperatorUI]] and the `dry-run` CLI can inspect it step-by-step:

1. **Temporal Trim & Reset**: `trim=start={start_sec}:duration={duration},setpts=PTS-STARTPTS` where `duration = min(BAND_SECONDS[duration_band], end_sec - start_sec)`.
2. **9:16 Aspect Crop**: `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`.
3. **Editorial Style Zoom**: `scale=iw*{zoom}:ih*{zoom},crop=1080:1920` (`dramatic` `1.12`, `educational` `1.00`, `commentary` `1.06`).
4. **Caption/Hook Burn-In (`drawbox` + `drawtext`)**:
   - Uses frame dimensions `iw`/`ih` inside `drawbox` (avoiding FFmpeg exit `234` where `w`/`h` self-reference the box).
   - Resolves a cross-platform system font (`_resolve_fontfile`: `C:/Windows/Fonts/arial.ttf`, `DejaVuSans-Bold.ttf`, etc.) and escapes `:` as `\:` so Windows FFmpeg builds without Fontconfig never crash (`0xC0000005` / `3221225477`).
5. **Audio Loudness Normalization**: `atrim=start={start_sec}:duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11` (EBU R128 `-16 LUFS`, `-1.5 dBTP`).
6. **Container & Codec**: `libx264` (`-preset fast -crf 20`), `aac` `128k`, `-movflags +faststart`.

If `REMOTION_URL` answers `POST /render` with a non-empty MP4, [[Remotion]] replaces `base_cut.mp4` before final packaging. See [[EXAMPLES]] for verified filtergraph output.
