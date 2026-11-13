---
tags:
  - pipeline
---

# Editing and FFmpeg rendering

[[Hooks]] supplies `hook_text`. [[Export]] stores the file and runs compliance on the duration that comes back. Styles and the Remotion service are in [[Models]].

`render_account_package` trims the source, scales and crops to 1080×1920, applies a style zoom (`dramatic` 1.12, `educational` 1.00, `commentary` 1.06), and optionally burns the hook with `drawtext`. Loudness target is `loudnorm=I=-16:TP=-1.5:LRA=11`. If `REMOTION_URL` answers `POST /render` with a non-empty file, that file replaces the FFmpeg cut. This audit left Remotion unset, so the cut is FFmpeg only.

```129:138:workers/video_rendering/render.py
    vf = (
        f"trim=start={start_sec}:duration={duration},"
        f"setpts=PTS-STARTPTS,"
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"scale=iw*{zoom}:ih*{zoom},"
        f"crop=1080:1920"
        f"{draw}"
    )
    af = f"atrim=start={start_sec}:duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11"
```

The commentary overlay used `drawbox`’s `w` and `h`. Those names are the box size, so FFmpeg exited 234 and wrote a 0-byte `video.mp4` plus `RENDER_ERROR.txt`. The filter now uses `iw` and `ih` for the frame. After that change, reprocessing the same upload wrote an 86,633-byte commentary MP4. Dramatic and educational had already rendered (87,386 and 82,060 bytes). The three previews are in [[EXAMPLES]].

`duration` passed to the trim is `min(band target, source window)`. The 15–25s band targets 20 seconds. A 4 second scene therefore exports 4 seconds, and compliance later rejects it when the brief asks for 20–45. That rejection is the gate working.

Next: [[Export]].
