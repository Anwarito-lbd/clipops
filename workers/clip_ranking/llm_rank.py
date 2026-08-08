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
from pathlib import Path
from typing import Any, Callable


def _ensure_env_loaded() -> None:
    """Put .env keys into os.environ if something else has not already.

    Settings are loaded through pydantic, which populates a settings object and
    never the process environment. This module reads os.environ directly, so any
    entrypoint that is not the API server - a worker, a maintenance script -
    found no key, and ranking degraded to keyword matching without the key ever
    being missing. That silent downgrade is the failure this project can least
    afford, so the keys are loaded here rather than left to the caller.
    """
    if os.environ.get("NVIDIA_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:  # dotenv absent: parse the handful of keys we need
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_ensure_env_loaded()

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

# Virality and safety pull in opposite directions: the most shareable moment in a
# stream is often the most dangerous one to post. Asked only for shock value, the
# model returned "Is that a Nazi flag?" as its top pick, reasoning that a
# controversial symbol creates tension - which is true, and would get the account
# banned. Platform policy has to be a hard constraint on selection, not a filter
# applied afterwards, because a rejected top pick wastes the whole ranking pass.
SAFETY_RULES = """
HARD EXCLUSIONS - never select a moment containing any of these, no matter how
engaging it is. These get accounts permanently banned, which costs far more than
any single clip earns:
- Hate symbols, extremist references, slurs, or discussion of either (including
  merely pointing one out or reacting to it)
- Gambling, betting, odds, or wagering amounts
- Violence, threats, weapons, or self-harm
- Illegal drugs, alcohol excess, tobacco or vaping
- Sexual content or objectifying commentary
- Financial advice framed as a guarantee, or specific profit promises
- Profanity in the hook_sentence, since that text is burned on screen
- Medical or health claims
- Anything mocking a person, group, nationality or religion

If a moment is engaging but touches any of the above, skip it and choose the next
best. Prefer moments that are engaging AND safe to post under a brand's name.
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

# Concurrent chunk requests. Bounded so a long video does not open a dozen
# simultaneous connections and trip the provider's rate limit, which would
# surface as 529s and drop the whole run back to keyword ranking.
CHUNK_CONCURRENCY = 4


class LLMUnavailable(RuntimeError):
    """Raised when no LLM backend is configured or reachable."""


class LLMBusy(LLMUnavailable):
    """Backend is momentarily overloaded — worth retrying, unlike a spent quota."""


# Overload and gateway errors clear on their own; a spent quota or bad key does
# not. Retrying the first costs seconds, while treating it as fatal drops clip
# selection to keyword scoring, which measurably picks filler over substance.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504, 529}
_RETRY_DELAYS = (2.0, 5.0, 12.0)


def _is_hard_quota(body: str) -> bool:
    """A 429 meaning "you are out of credit", not "slow down"."""
    low = (body or "").lower()
    return any(
        s in low
        for s in ("spending cap", "billing", "quota exceeded", "resource_exhausted",
                  "insufficient", "exceeded its monthly")
    )


def _call_with_retry(name: str, send, timeout_note: str = "") -> str:
    """Run a backend call, retrying only what is genuinely worth retrying."""
    import time

    last: Exception | None = None
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return send()
        except LLMBusy as exc:
            last = exc
            if delay is None:
                break
            time.sleep(delay)
        except LLMUnavailable:
            raise  # permanent for this backend — move on to the next
    raise LLMUnavailable(f"{name} still busy after {len(_RETRY_DELAYS)} retries: {last}")


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
        body = resp.text[:300]
        if resp.status_code in _TRANSIENT_STATUS and not _is_hard_quota(body):
            raise LLMBusy(f"Gemini HTTP {resp.status_code}: {body}")
        raise LLMUnavailable(f"Gemini HTTP {resp.status_code}: {body}")
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
        body = resp.text[:300]
        if resp.status_code in _TRANSIENT_STATUS and not _is_hard_quota(body):
            raise LLMBusy(f"NVIDIA HTTP {resp.status_code}: {body}")
        raise LLMUnavailable(f"NVIDIA HTTP {resp.status_code}: {body}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMUnavailable(f"Unexpected NVIDIA response: {str(resp.text)[:300]}") from exc


def default_llm(prompt: str) -> str:
    """NVIDIA first, Gemini as fallback.

    Gemini's free tier returns HTTP 429 once exhausted and needs a paid plan to
    continue, which silently dropped ranking back to keyword scoring mid-run.
    NVIDIA leads because it is the backend actually available; Gemini stays in
    the chain so it resumes automatically if its quota returns.
    """
    errors: list[str] = []
    for name, fn in (("nvidia", nvidia_llm), ("gemini", gemini_llm)):
        try:
            return _call_with_retry(name, lambda fn=fn: fn(prompt))
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


# A second, deterministic pass over whatever the model returns. The prompt asks
# for safe picks, but a prompt is a request and this is the failure that costs an
# account, so it is also enforced in code.
_UNSAFE_PATTERNS = (
    (re.compile(r"\bnazi|swastika|hitler|holocaust|kkk|white power|heil\b", re.I), "hate symbol or extremist reference"),
    # Betting is usually said in slang rather than named: "putting 5k on",
    # "throwing a stack on". Keyword-only matching let "We're putting $4,800 on
    # Portugal" through as safe.
    (re.compile(
        r"\bbet(?:ting|s)?\b|\bwager|\bodds\b|\bgambl|\bparlay|\bcasino|\bsportsbook"
        r"|\b(?:put|putting|throw|throwing|threw|drop|dropped|dropping"
        r"|slam|slammed|slamming|stak(?:e|ed|ing)|risk(?:ed|ing)?)\s+"
        r"(?:another\s+)?(?:[\$£€]\s*[\d,.]+|\d+\s*(?:k|grand|bands?|stacks?))\s+on\b"
        r"|\ball[- ]in on\b|\bhedge(?:d|ing)? (?:the )?bet", re.I), "gambling"),
    (re.compile(r"\bkill(?:ing|ed)?\b|\bshoot(?:ing)?\b|\bgun\b|\bweapon|\bstab|\bmurder|\bsuicide|\bkys\b", re.I), "violence or self-harm"),
    (re.compile(r"\bcocaine|\bheroin|\bmeth\b|\bweed\b|\bdrunk\b|\bvap(?:e|ing)|\bcigarette", re.I), "drugs, alcohol or tobacco"),
    (re.compile(r"\bguaranteed? (?:profit|return|money|win)|\brisk[- ]free\b|\bcan'?t lose\b", re.I), "financial guarantee"),
    (re.compile(r"\b(?:fuck|shit|bitch|cunt|nigg|faggot|retard)", re.I), "profanity"),
)


def safety_reject_reason(text: str) -> str | None:
    """Why this moment must not be posted, or None when it is clear."""
    for pattern, label in _UNSAFE_PATTERNS:
        if pattern.search(text or ""):
            return label
    return None


def filter_unsafe(highlights: list[dict], transcript: dict) -> tuple[list[dict], list[dict]]:
    """Split highlights into (safe, rejected).

    Checks the hook and title, and the transcript actually spoken inside the
    clip's window - a clean hook over an unusable segment is still unpostable,
    and the hook is what gets burned on screen.
    """
    segments = transcript.get("segments") or []
    safe, rejected = [], []
    for h in highlights:
        spoken = " ".join(
            (s.get("text") or "")
            for s in segments
            if _f(s.get("end")) >= h["start_time"] and _f(s.get("start")) <= h["end_time"]
        )
        reason = (
            safety_reject_reason(h.get("hook_sentence", ""))
            or safety_reject_reason(h.get("title", ""))
            or safety_reject_reason(spoken)
        )
        if reason:
            rejected.append({**h, "safety_reason": reason})
        else:
            safe.append(h)
    return safe, rejected


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

    def _rank_chunk(chunk: dict) -> tuple[list[dict], str | None]:
        text = build_transcript_text(chunk)
        if not text.strip():
            return [], None
        prompt = HIGHLIGHT_PROMPT.format(
            virality_criteria=VIRALITY_CRITERIA,
            content_type=content_info["content_type"],
            density=content_info["density"],
            min_sec=int(min_sec),
            max_sec=int(max_sec),
            min_clips=max(want * 2, 5),
            transcript=text,
        )
        error: str | None = "no valid highlights in response"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                parsed = _parse_json_loose(llm_fn(prompt))
                got = _sanitize(parsed.get("highlights"), duration, min_sec, max_sec)
                if got:
                    return got, None
            except LLMUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            if attempt < MAX_ATTEMPTS:
                prompt += (
                    "\n\nIMPORTANT: return ONLY valid JSON with a top-level "
                    "'highlights' array. No markdown fences, no commentary."
                )
        return [], error

    # Chunks are independent HTTP calls, so running them sequentially made a
    # long video cost chunks x per-call latency - about 900s on a reasoning
    # model. Results are reassembled in chunk order so ranking stays
    # deterministic.
    chunks = chunk_transcript(transcript)
    collected: list[dict] = []
    last_error = "no output"
    if len(chunks) == 1:
        got, err = _rank_chunk(chunks[0])
        collected.extend(got)
        last_error = err or last_error
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(len(chunks), CHUNK_CONCURRENCY)) as pool:
            for got, err in pool.map(_rank_chunk, chunks):
                collected.extend(got)
                if err:
                    last_error = err

    if not collected:
        raise LLMUnavailable(f"LLM produced no usable highlights: {last_error}")

    collected, unsafe = filter_unsafe(collected, transcript)
    if not collected:
        raise LLMUnavailable(
            "Every candidate was unsafe to post ("
            + ", ".join(sorted({u["safety_reason"] for u in unsafe}))
            + "). This source footage is not usable for a brand campaign."
        )

    deduped = dedupe_highlights(collected)
    for h in deduped:
        h["safety_rejected_count"] = len(unsafe)
    for h in deduped:
        h["content_type"] = content_info["content_type"]
    return deduped
