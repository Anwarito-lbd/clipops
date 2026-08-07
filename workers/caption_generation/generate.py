"""Account-specific captions and hooks — meaningfully different per style."""

from __future__ import annotations


def generate_account_copy(
    *,
    style: str,
    campaign_name: str,
    excerpt: str,
    hashtags: list[str],
    tags: list[str],
    disclosure: str | None,
    hook_variant: int = 1,
    # The line the ranker actually chose, drawn from what the speaker said.
    llm_hook: str | None = None,
    cta: str | None = None,
) -> dict[str, str]:
    excerpt_short = (excerpt or "this moment").strip()
    if len(excerpt_short) > 120:
        excerpt_short = excerpt_short[:117] + "..."

    hooks = {
        "dramatic": [
            f"Wait for it — {excerpt_short}",
            f"This hit different: {excerpt_short}",
            f"Nobody talks about this part of {campaign_name}",
        ],
        "educational": [
            f"Here's what {campaign_name} actually means",
            f"Quick breakdown: {excerpt_short}",
            f"3 things to notice in this clip",
        ],
        "commentary": [
            f"Okay but can we talk about this?",
            f"My honest take on {campaign_name}",
            f"Comment if you noticed this too",
        ],
    }
    # A ranker-chosen hook quotes what the speaker actually said, so it beats
    # any template. Captions previously read "Okay but can we talk about this?"
    # while the video itself displayed "I lost $135,000 in a single day" - the
    # good line existed and was simply thrown away here.
    style_hooks = hooks.get(style, hooks["dramatic"])
    hook = (llm_hook or "").strip() or style_hooks[(hook_variant - 1) % len(style_hooks)]

    context = {
        "dramatic": None,
        "educational": f"Context: short explainer for {campaign_name}.",
        "commentary": f"Reaction take — not a duplicate cut of the same edit.",
    }.get(style)

    # Lead with the hook. Opening on a disclosure buries the line that decides
    # whether anyone reads further.
    parts = [hook]
    if excerpt_short and style == "educational" and excerpt_short != hook:
        parts.append(excerpt_short)
    if style == "commentary":
        parts.append("Thoughts below.")
    if cta:
        parts.append(cta)
    parts.extend(tags)
    parts.extend(hashtags)
    if disclosure:
        parts.append(disclosure)
    caption = "\n\n".join(p for p in parts if p)

    return {
        "hook": hook,
        "caption": caption,
        "context_intro": context or "",
    }
