#!/usr/bin/env python3
"""Local-first TikTok/Instagram research note importer. Standard library only, except optional AI command."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlunparse

VAULT = Path(__file__).resolve().parent.parent
CLIP_DIR = VAULT / "02 Clips"
REPORT_PATH = VAULT / "09 Reports" / "Latest Report.md"
EXPORT_PATH = VAULT / "exports" / "clipper_edit_rules.json"
ALLOWED_HOSTS = {"tiktok.com", "instagram.com", "twitch.tv", "clips.twitch.tv", "youtube.com", "youtu.be"}
NUMERIC = ("views", "likes", "comments", "shares", "duration_seconds")
CATEGORIES = ("gta6", "streamer", "gaming", "other")


def normalize_url(raw):
    u = urlparse((raw or "").strip())
    host = (u.hostname or "").lower()
    if u.scheme not in ("https", "http") or not host or not any(host == d or host.endswith("." + d) for d in ALLOWED_HOSTS):
        raise ValueError("Expected a valid TikTok/Instagram/Twitch/YouTube public URL")
    if u.username or u.password or u.port:
        raise ValueError("URLs with credentials or ports are unsupported")
    # TikTok and Instagram share links often contain tracking query parameters.
    path = u.path.rstrip("/") or "/"
    # preserve tiktok shortlink paths; full canonical links are deduped by video ID below
    return urlunparse(("https", host, path, "", "", ""))


def identify(raw):
    url = normalize_url(raw)
    parsed = urlparse(url)
    host, path = parsed.hostname, parsed.path
    if host.endswith("tiktok.com"):
        match = re.search(r"/video/(\d+)", path)
        return "tiktok", "tt-" + (match.group(1) if match else hashlib.sha256(url.encode()).hexdigest()[:16]), url
    if host.endswith("instagram.com"):
        match = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", path)
        return "instagram", "ig-" + (match.group(1) if match else hashlib.sha256(url.encode()).hexdigest()[:16]), url
    if host.endswith("twitch.tv"):
        return "twitch", "tw-" + hashlib.sha256(url.encode()).hexdigest()[:16], url
    return "youtube", "yt-" + hashlib.sha256(url.encode()).hexdigest()[:16], url


def number_or_none(v):
    if v is None or str(v).strip() == "": return None
    text = str(v).replace(",", "").strip()
    if not text.isdigit(): raise ValueError(f"Invalid nonnegative number: {v!r}")
    return int(text)


def sanitize_line(text):
    return str(text or "").replace("\r", " ").replace("\n", " ").strip()[:1500]


def yaml_scalar(value):
    if value is None: return "null"
    if isinstance(value, bool): return "true" if value else "false"
    if isinstance(value, int): return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def validate_date(raw):
    if not raw: return ""
    try: return dt.date.fromisoformat(str(raw)).isoformat()
    except ValueError: raise ValueError(f"Date must be YYYY-MM-DD: {raw!r}")


def clip_file_for_uid(uid):
    files = list(CLIP_DIR.glob(f"{uid}*.md"))
    return files[0] if files else CLIP_DIR / f"{uid}.md"


def add_clip(data, quiet=False):
    platform, uid, url = identify(data.get("url"))
    category = sanitize_line(data.get("category", "other")).lower() or "other"
    if category not in CATEGORIES: raise ValueError(f"Category must be one of {CATEGORIES}")
    f = clip_file_for_uid(uid)
    if f.exists():
        if not quiet: print(f"Already in vault: {f.relative_to(VAULT)}")
        return f, False
    numbers = {k: number_or_none(data.get(k)) for k in NUMERIC}
    published = validate_date(data.get("posted_at"))
    observed = validate_date(data.get("observed_at")) or dt.datetime.now(dt.timezone.utc).date().isoformat()
    reviewed = str(data.get("reviewed", "false")).lower() in ("true", "1", "yes", "y")
    creator = sanitize_line(data.get("creator"))
    caption = sanitize_line(data.get("caption"))
    hook = sanitize_line(data.get("hook"))
    style = sanitize_line(data.get("style"))
    source = sanitize_line(data.get("source")) or "manual"
    props = {
        "type": "clip", "platform": platform, "category": category, "creator": creator,
        "url": url, "posted_at": published or None, "observed_at": observed,
        **numbers, "style": style, "hook": hook,
        "reviewed": reviewed, "source": source, "rights": "unknown",
    }
    meta = "\n".join(f"{k}: {yaml_scalar(v)}" for k,v in props.items())
    note = f"""---
{meta}
---
# Clip study: {uid}

**Original:** {url}  
**Creator:** {creator or 'Not supplied'}  
**Caption:** {caption or 'Not supplied'}  
**Status:** {'Research observations provided' if reviewed else 'Not visually/audio reviewed'}

## What happens in the video?
> Fill this only after opening the source. A URL alone does not reveal footage or sound.

| Time | Visual/action evidence | Text/voice/music actually heard | Editing mechanism |
|---|---|---|---|
| 0–2s | Not reviewed | Not reviewed | Not reviewed |
| 2–5s | Not reviewed | Not reviewed | Not reviewed |
| 5s–end | Not reviewed | Not reviewed | Not reviewed |

## Hypothesis to test
- **Hook**: {hook or 'Unknown — inspect video'}
- **Style**: {style or 'Unknown — inspect video'}
- **Payoff timing**:
- **Pacing / cuts**:
- **Beat sync / audio**:
- **Text/subtitles**:
- **Loop mechanism**:
- **Official footage vs fan edit/AI**:
- **Rights / permission**: Unknown; verify before reuse.

## Connect patterns
Add [[Beat Drop Reveal]], [[Cold Open Stakes]], [[Reaction Payoff]], [[Satisfying Loop]], or [[Visual Contrast]] only when directly supported by observation.

## Evidence and uncertainties
- Performance counts are snapshots, not live metrics.
- Video structure has not been automatically inspected.
"""
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(note, encoding="utf-8")
    if not quiet: print(f"Added: {f.relative_to(VAULT)}")
    return f, True


def read_frontmatter(path):
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"): return {}
    segment = content.split("\n---\n", 1)[0][4:]
    props = {}
    for line in segment.splitlines():
        if ":" not in line: continue
        key, val = line.split(":",1)
        val=val.strip()
        if val in ("null", ""): obj=None
        elif val in ("true", "false"): obj=val=="true"
        elif re.fullmatch(r"\d+",val): obj=int(val)
        elif val.startswith('"'):
            try: obj=json.loads(val)
            except json.JSONDecodeError: obj=val
        else: obj=val
        props[key.strip()]=obj
    return props


def all_clips():
    return [(p,read_frontmatter(p)) for p in sorted(CLIP_DIR.glob("*.md"))]


def engagement(d):
    if not all(isinstance(d.get(k),int) for k in ("views","likes","comments","shares")) or d["views"] <= 0: return None
    return 100 * (d["likes"]+d["comments"]+d["shares"]) / d["views"]


def shares_per_thousand(d):
    if not isinstance(d.get("views"),int) or not isinstance(d.get("shares"),int) or d["views"] <= 0: return None
    return d["shares"]*1000/d["views"]


def report():
    clips = all_clips()
    reviewed = sum(bool(x.get("reviewed")) for _,x in clips)
    metrics = [(p,d,engagement(d)) for p,d in clips if engagement(d) is not None]
    rows = []
    for p,d,e in sorted(metrics,key=lambda item:item[2],reverse=True):
        rows.append(f"| [[{p.stem}]] | {d.get('category','')} | {d.get('views',0):,} | {e:.2f}% | {d.get('style') or 'Unspecified'} |")
    categories = defaultdict(int)
    for _,d in clips: categories[d.get("category") or "other"] += 1
    lines = [
        "# Viral Edit Research Report", "",
        f"*Generated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*", "",
        f"- Clips catalogued: **{len(clips)}**",f"- Marked reviewed: **{reviewed}**",
        f"- Complete engagement snapshots: **{len(metrics)}**", "",
        "## Distribution by topic", "",
    ]
    lines += [f"- {k}: {v}" for k,v in sorted(categories.items())] or ["No clips yet."]
    lines += ["", "## Observed engagement snapshots (descriptive only)", "", "| Clip | Category | Views | Engagement rate | Style |", "|---|---|---:|---:|---|"]
    lines += rows or ["| No complete observations yet | — | — | — | — |"]
    if metrics:
        lines += ["", f"Median observed engagement rate across the complete sample: **{statistics.median([e for _,_,e in metrics]):.2f}%**."]
    lines += ["", "## Data quality / interpretation", "", "- Blank metrics mean **unknown**, not zero.", "- Engagement here = (likes + comments + shares) / views.", "- Sampling is not representative and cannot prove causation or predict viral success.", "- Metrics may be measured at very different post ages; compare carefully.", "- No TikTok feed was automatically searched or scraped.", ""]
    REPORT_PATH.parent.mkdir(parents=True,exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines),encoding="utf-8")
    print(f"Report updated: {REPORT_PATH.relative_to(VAULT)} ({len(clips)} clips)")


def rules():
    clips=all_clips()
    groups=defaultdict(list)
    for _,d in clips:
        e=engagement(d)
        if d.get('reviewed') and d.get('style') and e is not None:
            groups[d['style']].append(e)
    candidates=sorted([
        {"style":name,"sample_size":len(scores),"median_engagement_pct":round(statistics.median(scores),2),
         "confidence":"low—observational, non-causal"}
        for name,scores in groups.items() if len(scores)>=3
    ],key=lambda r:r['median_engagement_pct'],reverse=True)
    out={"schema_version":1,"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
         "clips_total":len(clips),"method":"manual observations only; requires 3+ reviewed clips with complete metrics per style",
         "candidate_edit_styles":candidates,"status":"research-candidates-only; not integrated with Twitch auto-clipper",
         "safety":"Use only authorized source video/audio. Review edits before publication."}
    EXPORT_PATH.parent.mkdir(parents=True,exist_ok=True)
    EXPORT_PATH.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Rules exported: {EXPORT_PATH.relative_to(VAULT)} ({len(candidates)} candidates)")


def ai_analyze(relative_path,model):
    path=(VAULT/relative_path).resolve()
    if not path.is_relative_to(CLIP_DIR.resolve()) or not path.is_file() or path.suffix!='.md':
        raise ValueError('Provide a note under 02 Clips, relative to the vault folder')
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError('Set OPENAI_API_KEY environment variable for optional API usage')
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('Install the optional package: pip install openai') from exc
    original=path.read_text(encoding='utf-8')
    if "\n## AI analysis (observations only)\n" in original:
        raise ValueError('This note already has an AI analysis. Remove that section before re-running.')
    instructions = (
        "Analyze only facts explicitly written in this supplied note. You have not seen the linked video, "
        "cannot hear the audio, and cannot access TikTok metrics beyond the note. "
        "Never invent timestamps, camera movements, sounds, visual content, account stats, or causal viral explanations. "
        "Separate Observed evidence, Hypotheses, Missing evidence, Suggested editing tests (authorized footage), "
        "and Confidence. If there are no real observations, say analysis is blocked pending human review."
    )
    client=OpenAI()
    resp=client.responses.create(model=model,instructions=instructions,input=original[:24000])
    content=(resp.output_text or '').strip()
    if not content: raise RuntimeError('The AI API returned no text; note left unchanged.')
    path.write_text(original.rstrip()+"\n\n## AI analysis (observations only)\n\n"+content+"\n",encoding='utf-8')
    print(f"AI analysis appended to {path.relative_to(VAULT)}")


def main():
    parser=argparse.ArgumentParser(description='Add and analyze public video reference notes in an Obsidian vault')
    cmd=parser.add_subparsers(dest='action',required=True)
    a=cmd.add_parser('add',help='Add one public video link as a structured note')
    a.add_argument('url')
    a.add_argument('--category',choices=CATEGORIES,default='other')
    for key in ('creator','caption','style','hook','posted-at','observed-at','source'):
        a.add_argument('--'+key)
    for key in NUMERIC: a.add_argument('--'+key.replace('_','-'))
    b=cmd.add_parser('import-csv',help='Import CSV references (no network access)')
    b.add_argument('path')
    cmd.add_parser('report',help='Write descriptive markdown report')
    cmd.add_parser('rules',help='Write editing rule candidates JSON')
    z=cmd.add_parser('ai-analyze',help='Analyze YOUR written observations using optional paid OpenAI API')
    z.add_argument('note_path',help='e.g., 02 Clips/tt-123.md')
    z.add_argument('--model',default='gpt-5.5')
    args=parser.parse_args()
    if args.action=='add':
        data={k.replace('-','_'):v for k,v in vars(args).items() if k not in ('action',)}
        add_clip(data)
    elif args.action=='import-csv':
        created=0; skipped=0
        with open(args.path,encoding='utf-8-sig',newline='') as f:
            for n,row in enumerate(csv.DictReader(f),2):
                if not row.get('url','').strip(): continue
                try:
                    _,was_created=add_clip(row,quiet=True)
                    created+=int(was_created);skipped+=int(not was_created)
                except ValueError as exc:
                    print(f'Invalid row {n}: {exc}')
        print(f'Imported {created} clip notes, skipped {skipped} duplicates')
    elif args.action=='report': report()
    elif args.action=='rules': rules()
    elif args.action=='ai-analyze': ai_analyze(args.note_path,args.model)

if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError,FileNotFoundError) as e:
        raise SystemExit(f'Error: {e}')
