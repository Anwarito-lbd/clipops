"""Grok (xAI) as the editor-in-the-loop: writes per-platform titles/captions and reviews each clip.

Set XAI_API_KEY (console.x.ai). XAI_MODEL picks the model; if unset we ask GET /v1/models and
use the newest-looking `grok-*` id. The API is OpenAI-compatible (POST /v1/chat/completions).

Review is a safety gate before auto-posting: it reads the transcript, chat reaction, title and
moment type and holds clips with slurs/hate, sexual content, doxxing or private info, minors,
graphic real-world violence, story spoilers, or misleading titles.
"""

from __future__ import annotations

import json
import os
import re

from .base import http

API = "https://api.x.ai/v1"

WRITER_PROMPT = """You write short-form video copy for a GTA 6 clip page that posts streamer moments.
Return ONLY JSON: {"title": str (<=70 chars, names the streamer, punchy, no spoilers, no false claims),
"hook": str (<=6 words, ALL CAPS, the on-screen line), "caption": str (1-2 sentences + 4-6 hashtags incl #GTA6),
"tiktok_caption": str (<=150 chars incl hashtags), "youtube_title": str (<=90 chars, ends with #Shorts)}.
Never reveal story/plot details. Credit the streamer. Do not invent events not in the transcript/chat."""

REVIEW_PROMPT = """You are the final safety check before a stream clip is auto-posted publicly.
Return ONLY JSON: {"decision": "approve" | "hold", "reasons": [str], "spoiler": bool}.
HOLD if any: slurs or hate speech; sexual content; doxxing, addresses, phone numbers, private info;
minors in unsafe situations; graphic real-world violence or self-harm; GTA 6 story/plot spoilers in the
title/caption/transcript; a title or caption that misrepresents what happens; harassment of a person.
Profanity, game violence and loud reactions are normal for this content -> approve."""


class Grok:
    def __init__(self, api_key: str | None = None, model: str | None = None, *, opener=None):
        self.api_key = api_key or os.environ.get("XAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("set XAI_API_KEY to use Grok")
        self.kw = {"opener": opener} if opener else {}
        self.model = model or os.environ.get("XAI_MODEL") or None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def models(self) -> list[str]:
        _, _, res = http("GET", f"{API}/models", headers=self._headers(), **self.kw)
        return sorted((m.get("id", "") for m in res.get("data", [])), reverse=True)

    def _model(self) -> str:
        if not self.model:
            grok = [m for m in self.models() if m.startswith("grok")]
            if not grok:
                raise RuntimeError("no grok model available to this key")
            self.model = grok[0]
        return self.model

    def chat_json(self, system: str, user: str) -> dict:
        _, _, res = http("POST", f"{API}/chat/completions", headers=self._headers(), timeout=90, json_body={
            "model": self._model(), "temperature": 0.4,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }, **self.kw)
        text = res["choices"][0]["message"]["content"]
        return parse_json_reply(text)

    @staticmethod
    def _context(manifest: dict) -> str:
        caps = " ".join(c["text"] for c in manifest.get("captions") or [])
        spike = manifest.get("spike") or {}
        return json.dumps({
            "streamer": manifest.get("streamer"), "game": "GTA 6",
            "moment_type": (manifest.get("moment") or {}).get("category"),
            "spoiler_risk_flag": (manifest.get("moment") or {}).get("spoiler_risk"),
            "transcript": caps[:2000] or "(no speech transcript)",
            "chat_reaction": spike.get("top_messages") or spike.get("top_terms"),
            "draft_title": (manifest.get("post") or {}).get("title"),
            "draft_hook": (manifest.get("post") or {}).get("hook"),
            "score": (manifest.get("rank") or {}).get("score"),
        })

    def write_post(self, manifest: dict) -> dict:
        out = self.chat_json(WRITER_PROMPT, self._context(manifest))
        return {k: str(v) for k, v in out.items() if k in
                ("title", "hook", "caption", "tiktok_caption", "youtube_title") and v}

    def review(self, manifest: dict, copy: dict | None = None) -> dict:
        ctx = json.loads(self._context(manifest))
        if copy:
            ctx["final_copy"] = copy
        out = self.chat_json(REVIEW_PROMPT, json.dumps(ctx))
        decision = str(out.get("decision", "hold")).lower()
        return {"decision": "approve" if decision == "approve" else "hold",
                "reasons": [str(r) for r in out.get("reasons") or []], "spoiler": bool(out.get("spoiler"))}


def parse_json_reply(text: str) -> dict:
    """Models sometimes wrap JSON in prose or ``` fences; take the first {...} block."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError(f"no JSON in model reply: {text[:200]}")
        return json.loads(m.group(0))
