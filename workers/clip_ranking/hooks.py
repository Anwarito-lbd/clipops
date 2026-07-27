"""Classify hook type for learning / analytics."""

from __future__ import annotations

import re

PATTERNS = [
    ("question", re.compile(r"\b(why|how|what|who|when|where|can we|did you)\b|\?", re.I)),
    ("surprising_fact", re.compile(r"\b(secret|nobody|surprising|actually|truth|fact)\b", re.I)),
    ("controversy", re.compile(r"\b(wrong|vs|versus|hate|controversial|debate|but)\b", re.I)),
    ("drama", re.compile(r"\b(wait|shocking|insane|crazy|hit different)\b", re.I)),
    ("payoff", re.compile(r"\b(so|therefore|result|finally|that'?s why)\b", re.I)),
]


def classify_hook(text: str) -> str:
    t = text or ""
    for name, rx in PATTERNS:
        if rx.search(t):
            return name
    return "generic"
