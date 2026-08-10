"""Assemble the operator-facing delivery folder for a campaign.

Internal render output is organised for the pipeline: keyed by account slot and
version id, with names the renderer and dashboard rely on. That is the wrong
shape for a human about to post twelve clips from a phone.

This builds a parallel, disposable folder in the shape the operator actually
works from - clip-01, clip-02 - with everything needed for one post in one
place, plus a proof file. The proof matters: timestamped evidence of what was
posted, from which source, under which campaign rules, is the only defence if a
submission's views are later disputed.

Nothing here is authoritative. It can be deleted and rebuilt from the renders at
any time.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def slugify(name: str, *, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", (name or "campaign").lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s or "campaign")[:max_len]


@dataclass
class PreparedClip:
    folder: str
    clip_number: int
    clip_version_id: str
    account_label: str
    score: float | None
    hook_text: str | None
    compliance_passed: bool | None
    files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hashtags_from(caption: str) -> list[str]:
    return [w for w in (caption or "").split() if w.startswith("#")]


def _proof_text(clip: dict[str, Any], campaign: dict[str, Any]) -> str:
    """Evidence of what was made, from what, under which rules."""
    req = campaign.get("requirements") or {}
    lines = [
        "CLIP PROVENANCE AND CAMPAIGN COMPLIANCE RECORD",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "CAMPAIGN",
        f"  Name         : {campaign.get('name')}",
        f"  URL          : {campaign.get('external_url') or '(not recorded)'}",
        f"  CPM          : {campaign.get('cpm')}",
        f"  Rules source : {req.get('source') or 'unknown'}",
        "",
        "SOURCE FOOTAGE",
        f"  File         : {clip.get('source_filename') or '(unknown)'}",
        f"  Segment      : {clip.get('start_sec')}s - {clip.get('end_sec')}s",
        f"  Transcript   : {clip.get('transcript_engine') or 'unknown'}",
        "",
        "CLIP",
        f"  Version id   : {clip.get('clip_version_id')}",
        f"  Account      : {clip.get('account_label')}",
        f"  Duration band: {clip.get('duration_band')}",
        f"  Content hash : {clip.get('content_hash') or '(none)'}",
        f"  Ranker       : {clip.get('ranker') or 'unknown'}",
        f"  Score        : {clip.get('score')}",
        "",
        "CAMPAIGN RULES APPLIED",
        f"  Hashtags req.: {', '.join(req.get('required_hashtags') or []) or '(none stated)'}",
        f"  Tags required: {', '.join(req.get('required_tags') or []) or '(none stated)'}",
        f"  Disclosure   : {req.get('required_disclosure') or '(none stated)'}",
        f"  Duration      : {req.get('min_duration_sec')}-{req.get('max_duration_sec')}s",
        "",
        "COMPLIANCE",
        f"  Result       : {'PASSED' if clip.get('compliance_passed') else 'NOT PASSED'}",
    ]
    for c in clip.get("compliance_checks") or []:
        mark = "PASS" if c.get("passed") else "FAIL"
        lines.append(f"    [{mark}] {c.get('name') or c.get('id')}: {c.get('detail') or ''}")
    lines += [
        "",
        "NOTE",
        "  Compliance checks caption text, duration and duplication. It does not",
        "  inspect the video for logos, on-screen CTAs or background music - those",
        "  remain the operator's responsibility to confirm before posting.",
    ]
    return "\n".join(lines)


def _summary_html(campaign_name: str, clips: list[PreparedClip], best: PreparedClip | None) -> str:
    rows = "\n".join(
        f"<tr><td>{c.folder}</td><td>{c.account_label}</td>"
        f"<td>{'-' if c.score is None else f'{c.score:.0f}'}</td>"
        f"<td>{'Passed' if c.compliance_passed else 'Review'}</td>"
        f"<td>{(c.hook_text or '')[:70]}</td></tr>"
        for c in clips
    )
    rec = (
        f"<p class=rec><strong>Recommended clip:</strong> {best.folder} "
        f"&middot; score {best.score:.0f}/100 &middot; "
        f"{'compliance passed' if best.compliance_passed else 'needs review'}</p>"
        if best and best.score is not None
        else "<p class=rec>No scored clips to recommend.</p>"
    )
    return f"""<!doctype html><meta charset=utf-8>
<title>{campaign_name} - ready to post</title>
<style>
body{{font:14px/1.5 system-ui,sans-serif;margin:2rem;max-width:900px}}
table{{border-collapse:collapse;width:100%;margin-top:1rem}}
th,td{{border:1px solid #ddd;padding:.5rem;text-align:left}}
th{{background:#f4f4f5}}
.rec{{background:#ecfdf5;border-left:4px solid #10b981;padding:.75rem}}
.note{{color:#666;font-size:12px;margin-top:1.5rem}}
</style>
<h1>{campaign_name}</h1>
{rec}
<table><tr><th>Clip</th><th>Account</th><th>Score</th><th>Compliance</th><th>Hook</th></tr>
{rows}</table>
<p class=note>Scores are the ranker's prediction of viral potential, not a
measurement. They have not yet been checked against real view counts. Compliance
covers caption text, duration and duplication only - confirm logos, on-screen
CTAs and music yourself before posting.</p>
"""


def prepare_campaign(
    *,
    out_root: Path,
    campaign: dict[str, Any],
    clips: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build ready_to_post/<campaign>/clip-NN/ for every exportable clip.

    Clips are ordered best-first so clip-01 is the one to post first.
    """
    folder = out_root / slugify(campaign.get("name") or "campaign")
    if folder.exists():
        shutil.rmtree(folder)  # rebuilt from renders; never the source of truth
    folder.mkdir(parents=True, exist_ok=True)

    ordered = sorted(clips, key=lambda c: (c.get("score") or 0), reverse=True)
    prepared: list[PreparedClip] = []

    # Numbering counts what is actually written, not what was considered. Tying
    # it to the input index left gaps whenever a clip was skipped - a failed
    # render with the top score produced a folder starting at clip-02.
    i = 0
    for clip in ordered:
        video = clip.get("video_path")
        if not video or not Path(video).is_file() or Path(video).stat().st_size == 0:
            continue  # a failed render has nothing to deliver

        i += 1
        sub = folder / f"clip-{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        shutil.copy2(video, sub / "final.mp4")
        written.append("final.mp4")

        caption = clip.get("caption") or ""
        (sub / "caption.txt").write_text(caption, encoding="utf-8")
        written.append("caption.txt")

        (sub / "hashtags.txt").write_text(
            "\n".join(_hashtags_from(caption)), encoding="utf-8"
        )
        written.append("hashtags.txt")

        cover = clip.get("cover_path")
        if cover and Path(cover).is_file():
            shutil.copy2(cover, sub / "cover.png")
            written.append("cover.png")

        (sub / "compliance-report.json").write_text(
            json.dumps(
                {
                    "passed": clip.get("compliance_passed"),
                    "checks": clip.get("compliance_checks") or [],
                    "not_verified": [
                        "logo presence",
                        "on-screen CTA",
                        "background music licensing",
                        "aspect ratio of the rendered file",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        written.append("compliance-report.json")

        (sub / "source-and-campaign-proof.txt").write_text(
            _proof_text(clip, campaign), encoding="utf-8"
        )
        written.append("source-and-campaign-proof.txt")

        prepared.append(
            PreparedClip(
                folder=f"clip-{i:02d}",
                clip_number=i,
                clip_version_id=clip.get("clip_version_id") or "",
                account_label=clip.get("account_label") or "",
                score=clip.get("score"),
                hook_text=clip.get("hook_text"),
                compliance_passed=clip.get("compliance_passed"),
                files=written,
            )
        )

    best = prepared[0] if prepared else None
    (folder / "campaign-summary.html").write_text(
        _summary_html(campaign.get("name") or "Campaign", prepared, best), encoding="utf-8"
    )

    return {
        "folder": str(folder),
        "clips": [p.to_dict() for p in prepared],
        "clip_count": len(prepared),
        "recommended": best.to_dict() if best else None,
        "summary_html": str(folder / "campaign-summary.html"),
    }
