"""Sentence-boundary snapping — the vendored tool must actually be reachable."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.clip_ranking.snap import snap_segments


def _transcript(words: list[tuple[str, float, float]]) -> dict:
    return {
        "engine": "whisperx",
        "segments": [
            {"words": [{"word": w, "start": s, "end": e} for w, s, e in words]}
        ],
    }


TRANSCRIPT = _transcript(
    [
        ("I", 0.0, 0.2),
        ("lost", 0.2, 0.5),
        ("everything.", 0.5, 1.0),
        ("Every", 1.2, 1.5),
        ("single", 1.5, 1.9),
        ("trade", 1.9, 2.3),
        ("is", 2.3, 2.5),
        ("one", 2.5, 2.8),
        ("outcome", 2.8, 3.3),
        ("on", 3.3, 3.5),
        ("a", 3.5, 3.6),
        ("long", 3.6, 4.0),
        ("timeline.", 4.0, 4.6),
    ]
)


def test_end_extends_to_complete_the_sentence():
    """The measured failure: a clip ending on '...one outcome on'."""
    out, adj = snap_segments(
        [{"start_sec": 1.2, "end_sec": 3.5}], TRANSCRIPT, max_sec=25.0
    )
    assert out[0]["end_sec"] > 4.0, "should extend past 'timeline.'"
    assert adj and adj[0]["delta_end_ms"] > 0


def test_snapping_never_exceeds_the_band_ceiling():
    out, _ = snap_segments([{"start_sec": 0.0, "end_sec": 4.2}], TRANSCRIPT, max_sec=2.0)
    assert out[0]["end_sec"] - out[0]["start_sec"] <= 2.0


def test_transcript_without_word_timestamps_is_left_alone():
    """A heuristic transcript has no words; snapping would invent boundaries."""
    out, adj = snap_segments(
        [{"start_sec": 1.0, "end_sec": 3.0}], {"engine": "heuristic", "segments": []}
    )
    assert out[0]["start_sec"] == 1.0 and out[0]["end_sec"] == 3.0
    assert adj == []


def test_other_segment_fields_survive():
    out, _ = snap_segments(
        [{"start_sec": 1.2, "end_sec": 3.5, "text": "keep me", "total_score": 97}],
        TRANSCRIPT,
    )
    assert out[0]["text"] == "keep me"
    assert out[0]["total_score"] == 97
