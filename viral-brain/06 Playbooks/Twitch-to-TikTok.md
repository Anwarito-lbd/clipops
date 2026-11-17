# Twitch → TikTok clipping strategy

## Separate the jobs
**Twitch moment detector**: chat surge, unique chatter increase, contextual message patterns; requests Twitch clips.

**TikTok reference brain** (this vault): studies formats, hooks, edits, source credit, and observed performance. It should **not** create Twitch clip requests based on TikTok engagement data without validation.

**Editor (future)**: takes a permitted video asset, performs transcript segmentation, selects vertical crop, generates accurate subtitles, executes a selected edit recipe, and queues a human review before publication.

## Candidate automation output
Run `python tools/brain.py rules` to export `exports/clipper_edit_rules.json`. It contains **data-informed candidates based only on real entered notes**, never unsupported 'winning styles'. If the sample is small, the file explicitly says so. It is **not automatically consumed by the earlier Twitch starter**.

## Event schema suggestion
```json
{
  "clip_url": "https://clips.twitch.tv/<clip-id>",
  "streamer": "authorized_channel",
  "detected_at": "2026-11-17T14:00:00Z",
  "chat_spike": 3.1,
  "reaction_terms": ["pog", "no way"],
  "permission": "confirm-clip-and-reuse-rights",
  "selected_edit_style": "cold-open-stakes",
  "edit_status": "needs-permitted-source-video"
}
```
The schema is an **illustration only**, not a real recorded clip.
