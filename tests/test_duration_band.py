"""duration_band comes from operator-editable text, so parsing must not raise.

A fixed {"15-25":20,"25-40":32,"40-60":50} lookup raised KeyError on an account
configured with "18-28" and failed every clip in a three-source run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.tasks import band_midpoint_sec


def test_known_bands_keep_their_previous_values():
    assert band_midpoint_sec("15-25") == 20
    assert band_midpoint_sec("40-60") == 50


def test_operator_defined_band_does_not_raise():
    assert band_midpoint_sec("18-28") == 23


def test_junk_falls_back_instead_of_raising():
    for band in (None, "", "banana", "25-", "-25", "0-0", "30-10"):
        assert band_midpoint_sec(band) == 20.0
