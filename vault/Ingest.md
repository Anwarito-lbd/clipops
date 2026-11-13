---
tags:
  - pipeline
---

# Ingest

Upstream of [[Transcription]]. Settings live in [[Config]]. A worked upload is in [[EXAMPLES]].

Two ways footage enters the pipeline:

- The Manifest V3 extension reads an already logged-in Content Rewards tab and posts discoveries to the API. It does not click Join, Submit, or Cash-out (`browser-extension/manifest.json`).
- The operator uploads a video. `POST /api/campaigns/{id}/assets` caps the body at `max_upload_mb`, rejects unexpected types, and sanitizes the filename before `process_asset` runs.

```64:87:apps/api/app/routers/pipeline.py
@router.post("/campaigns/{campaign_id}/assets", response_model=AssetOut)
async def upload_asset(
    campaign_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: str = Depends(require_operator),
):
    settings = get_settings()
    storage_root = Path(settings.storage_root)
    if not storage_root.is_absolute():
        storage_root = ROOT / storage_root

    # Stream with size cap — do not load unbounded into memory
    max_bytes = int(settings.max_upload_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            raise HTTPException(413, f"File exceeds max upload size ({settings.max_upload_mb} MB)")
        chunks.append(piece)
```

Approving a discovered campaign copies the brief into `campaigns` and `campaign_requirements`, then tells the operator to click Join themselves (`apps/api/app/routers/operator.py`, `approve_discovered`). The seeded “Exhausted Fake Engage” row is stored ineligible. In the local session its reject reasons included budget utilisation at 95%, a geography mismatch, and fake engagement.

Next: [[Transcription]].
