---
tags:
  - pipeline
---

# PySceneDetect Content & Adaptive Cut Detection

Upstream: [[Transcription]] · Downstream: [[Scoring]], [[RetentionPacing]] · UI Inspector: [[OperatorUI]]

Implemented in `workers/scene_detection/detect.py` (`detect_scenes`).

## Two Complementary Cut Detectors

1. **`ContentDetector(threshold=27.0, min_scene_len=15)`** — converts consecutive frames to HSV and flags a hard cut when the weighted delta across Hue, Saturation, and Value exceeds `27.0`. Ideal for clean editorial cuts and high-contrast scene transitions.
2. **`AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=15)`** — compares the current frame's content score against a rolling temporal window of neighboring frames. Resists false triggers from rapid camera pans or talking-head motion while catching genuine editorial cuts.
3. **`hybrid` mode (default in [[OperatorUI]])** — runs `AdaptiveDetector` first and automatically falls back to `ContentDetector` if `<= 1` scene is found, ensuring both dynamic vlogs and static synthetic test reels split cleanly.

## Fixed-Window Fallback

If `scenedetect` is unavailable or fails on malformed streams, `detect_scenes` probes duration via `ffprobe` and emits deterministic `8.0s` windows (`detector: "fixed_window"`), capping empty outputs to `[0.0, min(15.0, dur)]`.

Scene boundaries define the candidate cut windows consumed by [[Scoring]] and displayed on the proportional timeline in [[OperatorUI]]. See [[EXAMPLES]] for observed cut boundaries on the 24s multi-scene demo.
