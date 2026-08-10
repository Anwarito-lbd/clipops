"""Word-level burned captions for the body of a clip.

Until now a clip showed a hook for the opening seconds and then nothing at all
for the remaining twenty. Short-form clips carry captions throughout; word-level
timing already exists in the whisperx transcript and was simply never used.

Density is the thing that makes captions read as professional rather than as a
wall of text: two to four words on screen at a time, grouped at natural pauses,
never in the bottom fifth where TikTok's own UI sits.
"""

from __future__ import annotations

from typing import Any

# 1-4 words per screen is the short-form convention. Four keeps a line readable
# at the font size a phone needs without a second line.
MAX_WORDS_PER_GROUP = 4

# A gap longer than this ends a group even when it is under the word cap - the
# break belongs where the speaker paused.
PAUSE_SEC = 0.35


def words_in_window(
    transcript: dict[str, Any], start_sec: float, end_sec: float
) -> list[dict[str, Any]]:
    """Word entries inside [start_sec, end_sec), with times relative to the clip."""
    out: list[dict[str, Any]] = []
    for seg in transcript.get("segments") or []:
        for w in seg.get("words") or []:
            ws, we = w.get("start"), w.get("end")
            text = str(w.get("word", "")).strip()
            if ws is None or we is None or not text:
                continue
            if ws < start_sec or ws >= end_sec:
                continue
            out.append(
                {
                    "text": text,
                    "start": round(ws - start_sec, 3),
                    "end": round(min(we, end_sec) - start_sec, 3),
                }
            )
    out.sort(key=lambda w: w["start"])
    return out


def group_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Batch words into short on-screen phrases, breaking at pauses and sentence ends."""
    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        groups.append(
            {
                "text": " ".join(w["text"] for w in current),
                "start": current[0]["start"],
                "end": current[-1]["end"],
            }
        )
        current.clear()

    for i, w in enumerate(words):
        current.append(w)
        ends_sentence = w["text"].rstrip()[-1:] in ".?!"
        next_gap = (
            words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0.0
        )
        if ends_sentence or len(current) >= MAX_WORDS_PER_GROUP or next_gap > PAUSE_SEC:
            flush()
    flush()
    return groups
