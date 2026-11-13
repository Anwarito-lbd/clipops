---
tags:
  - pipeline
---

# Hook detection

[[Scoring]] already counts hook words. This note is the classifier and the caption writer that run after a segment is selected. The rendered line is burned in by [[Editing]].

```7:22:workers/clip_ranking/hooks.py
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
```

The first matching pattern wins. On the offline demo, the 8–12s window contained “surprising” and was classified `surprising_fact`. The earlier windows contained “what” and were classified `question`.

Selected clips are assigned round-robin across active TikTok accounts. Each account style gets a different hook template from `generate_account_copy`. They are not three copies of one edit.

```192:204:apps/api/app/tasks.py
        # Assign best clips to accounts round-robin — NOT 3 variants of every candidate
        for idx, cand in enumerate(selected):
            account = accounts[idx % len(accounts)]
            hook_type = classify_hook(cand.transcript_excerpt or "")
            copy = generate_account_copy(
                style=account.style or "dramatic",
                campaign_name=campaign.name,
                excerpt=cand.transcript_excerpt or "",
                hashtags=list((live_req.required_hashtags if live_req else []) or []),
                tags=list((live_req.required_tags if live_req else []) or []),
                disclosure=(live_req.required_disclosure if live_req else None),
                hook_variant=(idx % 3) + 1,
            )
```

The local API session produced three `REVIEW_REQUIRED` versions: commentary “Okay but can we talk about this?”, dramatic “This hit different: …”, and educational “3 things to notice in this clip”. Full text is in [[EXAMPLES]].

Next: [[Editing]].
