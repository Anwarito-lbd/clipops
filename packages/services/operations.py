"""Footage intake, campaign rotation, and storage reclamation.

Three chores that otherwise fall on the operator every day:
  - getting downloaded footage into a campaign without clicking through an
    upload form
  - noticing that a campaign is nearly exhausted *before* it dries up
  - deleting source video that is no longer needed, since a single Twitch VOD
    can outweigh every export the campaign will ever produce
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage_security import ALLOWED_VIDEO_EXTENSIONS, sanitize_filename

# Warn while there is still time to line up a replacement, not once it is gone.
ROTATE_WARN_AT = 0.75
EXHAUSTED_AT = 0.95

# Statuses meaning a clip has left the building; its source is no longer needed.
_DONE_STATUSES = {"MANUALLY_POSTED", "SUBMITTED", "PAID", "REJECTED"}


@dataclass
class InboxItem:
    path: str
    filename: str
    size_bytes: int
    campaign_id: str | None
    campaign_name: str | None
    problem: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def scan_inbox(inbox_root: Path, campaigns_by_id: dict[str, str]) -> list[InboxItem]:
    """List droppable footage.

    Files go in ``inbox/<campaign_id>/`` to be routed automatically; anything
    loose in ``inbox/`` is reported without a campaign so the operator can
    assign it. Nothing is moved here - this only reports what is waiting.
    """
    items: list[InboxItem] = []
    if not inbox_root.exists():
        return items

    for path in sorted(inbox_root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue

        rel = path.relative_to(inbox_root)
        folder = rel.parts[0] if len(rel.parts) > 1 else None
        campaign_id = folder if folder in campaigns_by_id else None

        problem = None
        if path.suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
            problem = f"Not a video file ({path.suffix or 'no extension'})"
        elif path.stat().st_size == 0:
            problem = "Empty file"
        elif folder and campaign_id is None:
            problem = f"Folder '{folder}' is not a known campaign id"
        elif campaign_id is None:
            problem = "Loose file - move it into inbox/<campaign_id>/ or assign it"

        items.append(
            InboxItem(
                path=str(path),
                filename=path.name,
                size_bytes=path.stat().st_size,
                campaign_id=campaign_id,
                campaign_name=campaigns_by_id.get(campaign_id or ""),
                problem=problem,
            )
        )
    return items


def import_inbox_file(src: Path, storage_root: Path, campaign_id: str) -> tuple[Path, str]:
    """Move a dropped file into the campaign's source folder.

    Moves rather than copies: the operator already has the original from the
    campaign's resources, and duplicating multi-GB footage to keep a second copy
    in an inbox nobody reads is how disks fill up.
    """
    safe = sanitize_filename(src.name)
    dest_rel = Path("sources") / campaign_id / safe
    dest = storage_root / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Never silently overwrite footage already imported under the same name.
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        dest = dest.with_name(f"{stem}-{stamp}{suffix}")
        dest_rel = dest.relative_to(storage_root)

    shutil.move(str(src), str(dest))
    return dest, dest_rel.as_posix()


@dataclass
class RotationSignal:
    campaign_id: str
    campaign_name: str
    budget_used_pct: float | None
    cap_used_pct: float | None
    state: str  # healthy | rotate_soon | exhausted
    reason: str
    clips_posted: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def rotation_signal(
    *,
    campaign_id: str,
    campaign_name: str,
    total_budget: float | None,
    budget_utilised: float | None,
    max_payout: float | None,
    earned_so_far: float,
    clips_posted: int,
) -> RotationSignal:
    """Whether a campaign is worth continuing to feed.

    Two independent ceilings apply: the campaign's shared budget, which any
    clipper can exhaust, and your own per-clipper payout cap. Whichever binds
    first ends the campaign for you.
    """
    budget_pct = None
    if total_budget and total_budget > 0 and budget_utilised is not None:
        budget_pct = min(1.0, budget_utilised / total_budget)

    cap_pct = None
    if max_payout and max_payout > 0:
        cap_pct = min(1.0, earned_so_far / max_payout)

    worst = max([p for p in (budget_pct, cap_pct) if p is not None], default=None)

    if worst is None:
        return RotationSignal(
            campaign_id, campaign_name, budget_pct, cap_pct, "healthy",
            "No budget or cap figures captured yet - pull the brief to track this",
            clips_posted,
        )
    if worst >= EXHAUSTED_AT:
        which = "your payout cap" if cap_pct == worst else "the campaign budget"
        return RotationSignal(
            campaign_id, campaign_name, budget_pct, cap_pct, "exhausted",
            f"{which} is {worst:.0%} spent - stop producing and switch campaigns",
            clips_posted,
        )
    if worst >= ROTATE_WARN_AT:
        which = "your payout cap" if cap_pct == worst else "the campaign budget"
        return RotationSignal(
            campaign_id, campaign_name, budget_pct, cap_pct, "rotate_soon",
            f"{which} is {worst:.0%} spent - line up a replacement in the same lane now",
            clips_posted,
        )
    return RotationSignal(
        campaign_id, campaign_name, budget_pct, cap_pct, "healthy",
        f"{worst:.0%} spent - keep going", clips_posted,
    )


@dataclass
class ReclaimCandidate:
    campaign_id: str
    campaign_name: str
    paths: list[str]
    bytes_freed: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_reclaimable_sources(
    *,
    storage_root: Path,
    campaigns: list[dict[str, Any]],
) -> list[ReclaimCandidate]:
    """Source footage that is finished with, largest first.

    Only source video is ever proposed for deletion. Exports are kept
    permanently: they are the evidence in a view dispute, and they are small
    next to the multi-gigabyte originals they came from.

    A campaign's sources are reclaimable only when every clip made from them has
    been posted or resolved, and the campaign itself is exhausted. Anything still
    awaiting review or approval is left alone, since it may need re-rendering.
    """
    out: list[ReclaimCandidate] = []
    for c in campaigns:
        if not c.get("exhausted"):
            continue
        versions = c.get("version_statuses") or []
        if not versions:
            continue
        unfinished = [s for s in versions if s not in _DONE_STATUSES]
        if unfinished:
            continue

        paths, total = [], 0
        for rel in c.get("source_paths") or []:
            p = storage_root / rel
            if p.is_file():
                paths.append(str(p))
                total += p.stat().st_size
        if not paths:
            continue

        out.append(
            ReclaimCandidate(
                campaign_id=c["id"],
                campaign_name=c.get("name") or "",
                paths=paths,
                bytes_freed=total,
                reason=(
                    f"Campaign finished; all {len(versions)} clip(s) posted or resolved. "
                    "Exports and captions are kept."
                ),
            )
        )
    out.sort(key=lambda r: r.bytes_freed, reverse=True)
    return out


def human_bytes(n: int) -> str:
    step = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if step < 1024 or unit == "TB":
            return f"{step:.1f} {unit}" if unit != "B" else f"{int(step)} B"
        step /= 1024
    return f"{step:.1f} TB"
