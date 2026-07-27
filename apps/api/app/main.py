from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import init_db
from app.routers import campaigns, pipeline, operator
from app.schemas import HealthOut

settings = get_settings()

app = FastAPI(
    title="ClipOps API",
    version="0.2.0",
    description="Operator Mode: AI assist → human approve → manual post/submit/cash-out → automatic tracking",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + [
        "chrome-extension://*",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"chrome-extension://.*|http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(campaigns.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(operator.router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut()
