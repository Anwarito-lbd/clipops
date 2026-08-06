"""LLM-based viral highlight detection.

The regex ranker in rank.py counts keywords, which cannot distinguish a genuine
opinion bomb from a sentence that happens to contain "but". This module asks a
language model to read the transcript and pick the moments worth clipping,
returning a score, the exact hook line, and why it works.

Design notes:
  - Over-generate then dedupe. We ask for roughly 2x the clips we want so the
    overlap filter has something to choose between.
  - Targets 15-25s. TikTok's 2026 viral threshold is ~70% completion, and a
    48-second clip does not clear that bar.
  - Backend is pluggable via `llm_fn`. Gemini is the default because it has a
    free tier; swapping to another provider is one function.
  - Every failure path falls back to the regex ranker rather than raising, so a
    missing key or a rate limit degrades quality instead of breaking the run.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

LLMFn = Callable[[str], str]

# Ranked by impact on short-form performance.
VIRALITY_CRITERIA = """
Virality signals to prioritise (ranked by impact):
1. HOOK MOMENTS - statements creating immediate curiosity ("The secret is...", "Nobody talks about...", "I was completely wrong about...")
2. EMOTIONAL PEAKS - genuine surprise, laughter, anger, vulnerability; raw unscripted reactions
3. OPINION BOMBS - strong, polarising or counter-intuitive claims that trigger agree/disagree
4. REVELATION MOMENTS - surprising facts, stats or confessions that reframe how the viewer thinks
5. CONFLICT/TENSION - disagreement, pushback, or a problem confronted head-on
6. QUOTABLE ONE-LINERS - a sentence that stands alone as a quote card
7. STORY PEAKS - the climax or twist of an anecdote; the payoff
8. PRACTICAL VALUE - a concrete tip or insight the viewer can apply immediately
"""

CONTENT_TYPE_PROMPT = """Classify this video transcript.
content_type: one of podcast, interview, tutorial, lecture, commentary, debate, vlog, music, sports, other.
density: low (mostly filler/chit-chat), medium, or high (dense info/stories).
Respond with JSON only: {"content_type": "...", "density": "..."}"""

HIGHLIGHT_PROMPT = """You are an elite short-form video editor who has studied thousands of viral TikTok clips. You know exactly what makes viewers stop scrolling, watch to the end, and share.
{virality_criteria}
Content type: {content_type} | Density: {density}

Find the most viral-worthy moments in this transcript.

Rules:
- TARGET DURATION {min_sec}-{max_sec} SECONDS. This is a hard requirement: TikTok rewards completion rate above all else, and longer clips do not get watched to the end. Only exceed {max_sec}s if a single thought genuinely cannot be cut shorter.
- Every clip must open with a strong HOOK that lands within the FIRST 1.5 SECONDS. Viewers decide that fast.
- Never cut mid-sentence or mid-thought. Each clip must feel complete and self-contained, understandable with zero context.
- Clips must not overlap each other significantly.
- Score 0-100 on VIRAL potential specifically, not general quality or informativeness.
- Generate at least {min_clips} highlights.
- For each, give "hook_sentence": the exact opening line that stops the scroll. This gets burned on screen, so keep it under 60 characters.
- Give "virality_reason": one sentence on why this clip works.

Timestamps are in seconds and must fall inside the transcript.

Respond ONLY with valid JSON, no markdown fences, no commentary:
{{"highlights":[{{"title":"string","start_time":float,"end_time":float,"score":int,"hook_sentence":"string","virality_reason":"string"}}]}}

Transcript:
{transcript}"""

# Chunk long transcripts so the model sees the whole video without one huge call.
CHUNK_SIZE_SECONDS = 1200
LONG_VIDEO_THRESHOLD = 1800
CHUNK_OVERLAP_SECONDS = 60
OVERLAP_REJECT_RATIO = 0.5
MAX_ATTEMPTS = 3


class LLMUnavailable(RuntimeError):
    """Raised when no LLM backend is configured or reachable."""


def gemini_llm(prompt: str, *, model: str | None = None, timeout: float = 120.0) -> str:
    """Call Gemini via REST. Avoids adding an SDK dependency."""
    import httpx

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise LLMUnavailable("GEMINI_API_KEY is not set")

    # Pinned rather than "-latest": a model swap underneath would silently change
    # clip selection quality. Bump deliberately.
    model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }
    resp = httpx.post(
        url,
        json=payload,
        headers={"x-goog-api-key": api_key},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise LLMUnavailable(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise LLMUnavailable(f"Unexpected Gemini response shape: {str(data)[:300]}") from exc


def nvidia_llm(prompt: str, *, model: str | None = None, timeout: float = 180.0) -> str:
    """Call NVIDIA's OpenAI-compatible endpoint. Used when Gemini is unavailable."""
    import httpx

    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise LLMUnavailable("NVIDIA_API_KEY is not set")

    model = model or os.environ.get("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash")
    resp = httpx.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 8192,
            "stream": False,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise LLMUnavailable(f"NVIDIA HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMUnavailable(f"Unexpected NVIDIA response: {str(resp.text)[:300]}") from exc


def default_llm(prompt: str) -> str:
    """Gemini first, NVIDIA as fallback.

    Ranking runs a handful of times per source video, so a rate limit on one
    free tier should degrade to the other rather than dropping the whole batch
    back to keyword scoring.
    """
    errors: list[str] = []
    for name, fn in (("gemini", gemini_llm), ("nvidia", nvidia_llm)):
        try:
            return fn(prompt)
        except LLMUnavailable as exc:
            errors.append(f"{name}: {exc}")
    raise LLMUnavailable(" | ".join(errors) or "no LLM backend configured")


def _parse_json_loose(raw: str) -> dict:
    """Models sometimes wrap JSON in markdown fences despite instructions."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_transcript_text(transcript: dict) -> str:
    segments = transcript.get("segments") or []
    return "\n".join(
        f"[{_f(s.get('start')):.1f}s] {(s.get('text') or '').strip()}" for s in segments
    )


def transcript_duration(transcript: dict) -> float:
    segments = transcript.get("segments") or []
    if not segments:
        return 0.0
    return _f(transcript.get("duration")) or _f(segments[-1].get("end"))


def chunk_transcript(transcript: dict) -> list[dict]:
    """Split long transcripts into overlapping windows so nothing is missed."""
    duration = transcript_duration(transcript)
    if duration <= LONG_VIDEO_THRESHOLD:
        return [transcript]

    segments = transcript.get("segments") or []
    chunks: list[dict] = []
    start = 0.0
    while start < duration:
        end = min(start + CHUNK_SIZE_SECONDS, duration)
        chunk_segs = [
            s
            for s in segments
            if _f(s.get("start")) >= start and _f(s.get("end")) <= end + CHUNK_OVERLAP_SECONDS
        ]
        if chunk_segs:
            chunk = dict(transcript)
            chunk["segments"] = chunk_segs
            chunks.append(chunk)
        start += CHUNK_SIZE_SECONDS - CHUNK_OVERLAP_SECONDS
    return chunks or [transcript]


def _sanitize(raw_highlights: Any, duration: float, min_sec: float, max_sec: float) -> list[dict]:
    """Normalise model output; drop anything unusable rather than guessing."""
    if not isinstance(raw_highlights, list):
        return []
    out: list[dict] = []
    for item in raw_highlights:
        if not isinstance(item, dict):
            continue
        start = _f(item.get("start_time"), -1.0)
        end = _f(item.get("end_time"), -1.0)
        if start < 0 or end <= start:
            continue
        if duration > 0:
            start = min(start, duration)
            end = min(end, duration)
            if end <= start:
                continue
        # Trim an over-long pick rather than discarding a good moment.
        if end - start > max_sec:
            end = start + max_sec
        if end - start < min_sec:
            continue
        score = item.get("score")
        try:
            score_i = max(0, min(100, int(float(score))))
        except (TypeError, ValueError):
            score_i = 0
        out.append(
            {
                "title": str(item.get("title") or "Untitled").strip()[:200],
                "start_time": start,
                "end_time": end,
                "score": score_i,
                "hook_sentence": str(item.get("hook_sentence") or "").strip()[:200],
                "virality_reason": str(item.get("virality_reason") or "").strip()[:400],
            }
        )
    return out


def detect_content_type(transcript: dict, llm_fn: LLMFn) -> dict[str, str]:
    segments = transcript.get("segments") or []
    sample = " ".join((s.get("text") or "") for s in segments[:25])[:3000]
    try:
        parsed = _parse_json_loose(llm_fn(f"{CONTENT_TYPE_PROMPT}\n\nTranscript sample:\n{sample}"))
        return {
            "content_type": str(parsed.get("content_type") or "other"),
            "density": str(parsed.get("density") or "medium"),
        }
    except Exception:
        return {"content_type": "other", "density": "medium"}


def dedupe_highlights(highlights: list[dict]) -> list[dict]:
    """Drop a clip overlapping >50% with a higher-scoring one already kept."""
    ordered = sorted(highlights, key=lambda h: h.get("score", 0), reverse=True)
    kept: list[dict] = []
    for h in ordered:
        h_start, h_end = h["start_time"], h["end_time"]
        h_dur = max(h_end - h_start, 0.001)
        clash = False
        for k in kept:
            overlap = min(h_end, k["end_time"]) - max(h_start, k["start_time"])
            if overlap > 0 and overlap / h_dur > OVERLAP_REJECT_RATIO:
                clash = True
                break
        if not clash:
            kept.append(h)
    return kept


def find_highlights(
    transcript: dict,
    *,
    want: int = 5,
    min_sec: float = 15.0,
    max_sec: float = 25.0,
    llm_fn: LLMFn | None = None,
) -> list[dict]:
    """Return deduped highlights, best first.

    Asks for ~2x `want` so dedupe has real choices. Raises LLMUnavailable if the
    backend cannot produce usable output; callers fall back to the regex ranker.
    """
    llm_fn = llm_fn or default_llm
    duration = transcript_duration(transcript)
    content_info = detect_content_type(transcript, llm_fn)

    collected: list[dict] = []
    last_error = "no output"
    for chunk in chunk_transcript(transcript):
        text = build_transcript_text(chunk)
        if not text.strip():
            continue
        prompt = HIGHLIGHT_PROMPT.format(
            virality_criteria=VIRALITY_CRITERIA,
            content_type=content_info["content_type"],
            density=content_info["density"],
            min_sec=int(min_sec),
            max_sec=int(max_sec),
            min_clips=max(want * 2, 5),
            transcript=text,
        )
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                parsed = _parse_json_loose(llm_fn(prompt))
                got = _sanitize(parsed.get("highlights"), duration, min_sec, max_sec)
                if got:
                    collected.extend(got)
                    break
                last_error = "no valid highlights in response"
            except LLMUnavailable:
                raise
            except Exception as exc:
                last_error = str(exc)
            if attempt < MAX_ATTEMPTS:
                prompt += (
                    "\n\nIMPORTANT: return ONLY valid JSON with a top-level "
                    "'highlights' array. No markdown fences, no commentary."
                )

    if not collected:
        raise LLMUnavailable(f"LLM produced no usable highlights: {last_error}")

    deduped = dedupe_highlights(collected)
    for h in deduped:
        h["content_type"] = content_info["content_type"]
    return deduped
