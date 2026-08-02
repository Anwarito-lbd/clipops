from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    handle: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    style: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    audience_geo: Mapped[list[Any]] = mapped_column(JSON, default=list)
    audience_notes: Mapped[Optional[str]] = mapped_column(Text)
    preferred_clip_length: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    preferred_hooks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(256))
    external_url: Mapped[Optional[str]] = mapped_column(String(1024))
    raw_brief: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    cpm: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    total_budget: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    budget_utilised: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), default=0)
    budget_remaining: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    eligibility: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    required_geo: Mapped[list[Any]] = mapped_column(JSON, default=list)
    has_rights: Mapped[bool] = mapped_column(Boolean, default=True)
    footage_quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    requirement_simplicity_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    viral_potential_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    audience_match_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    competition_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    approval_probability: Mapped[float] = mapped_column(Numeric(5, 4), default=0.7)
    expected_views: Mapped[float] = mapped_column(Numeric(14, 2), default=10000)
    estimated_production_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=15)
    score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    expected_profit: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    reject_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requirements: Mapped[list["CampaignRequirement"]] = relationship(back_populates="campaign")


class CampaignRequirement(Base):
    __tablename__ = "campaign_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"))
    required_hashtags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    required_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    required_disclosure: Mapped[Optional[str]] = mapped_column(Text)
    disclosure_placement: Mapped[str] = mapped_column(String(64), default="beginning")
    min_duration_sec: Mapped[int] = mapped_column(Integer, default=15)
    max_duration_sec: Mapped[int] = mapped_column(Integer, default=60)
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="9:16")
    forbidden_words: Mapped[list[Any]] = mapped_column(JSON, default=list)
    forbidden_claims: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requires_logo: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_cta: Mapped[bool] = mapped_column(Boolean, default=False)
    cta_text: Mapped[Optional[str]] = mapped_column(Text)
    posting_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    no_external_music: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_immutable_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="requirements")


class SourceAsset(Base):
    __tablename__ = "source_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128))
    duration_sec: Mapped[Optional[float]] = mapped_column(Float)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="IMPORTED")
    transcript_path: Mapped[Optional[str]] = mapped_column(String(1024))
    scenes_path: Mapped[Optional[str]] = mapped_column(String(1024))
    # whisperx | faster-whisper | heuristic — "heuristic" means ASR failed and the
    # transcript is placeholder text, not speech.
    transcript_engine: Mapped[Optional[str]] = mapped_column(String(32))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClipCandidate(Base):
    __tablename__ = "clip_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_assets.id", ondelete="CASCADE"))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"))
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    transcript_excerpt: Mapped[Optional[str]] = mapped_column(Text)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_score: Mapped[float] = mapped_column(Float, default=0)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClipVersion(Base):
    __tablename__ = "clip_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("clip_candidates.id", ondelete="CASCADE"))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"))
    social_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_accounts.id"))
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_band: Mapped[str] = mapped_column(String(16), nullable=False)
    hook_variant: Mapped[int] = mapped_column(Integer, default=1)
    subtitle_style: Mapped[str] = mapped_column(String(32), default="bold")
    caption: Mapped[Optional[str]] = mapped_column(Text)
    hook_text: Mapped[Optional[str]] = mapped_column(Text)
    context_intro: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="GENERATED")
    # Carried from the source asset so the approve/export gate can refuse clips
    # whose captions came from a fabricated transcript.
    transcript_engine: Mapped[Optional[str]] = mapped_column(String(32))
    fabrication_override_reason: Mapped[Optional[str]] = mapped_column(Text)
    requirements_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("campaign_requirements.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Render(Base):
    __tablename__ = "renders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clip_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("clip_versions.id", ondelete="CASCADE"))
    account_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    video_path: Mapped[Optional[str]] = mapped_column(String(1024))
    caption_path: Mapped[Optional[str]] = mapped_column(String(1024))
    cover_path: Mapped[Optional[str]] = mapped_column(String(1024))
    checklist_path: Mapped[Optional[str]] = mapped_column(String(1024))
    package_dir: Mapped[Optional[str]] = mapped_column(String(1024))
    content_hash: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="GENERATED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clip_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("clip_versions.id", ondelete="CASCADE"))
    render_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("renders.id", ondelete="SET NULL"))
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    checks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    override_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clip_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("clip_versions.id", ondelete="CASCADE"))
    social_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_accounts.id"))
    tiktok_url: Mapped[Optional[str]] = mapped_column(String(1024))
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="EXPORTED")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("posts.id", ondelete="CASCADE"))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"))
    content_rewards_url: Mapped[Optional[str]] = mapped_column(String(1024))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="SUBMITTED")
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("posts.id", ondelete="CASCADE"))
    metric_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Earning(Base):
    __tablename__ = "earnings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id", ondelete="CASCADE"))
    provisional_amount: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    validated_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    fee_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    net_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="EARNING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    earnings_id: Mapped[str] = mapped_column(String(36), ForeignKey("earnings.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="PAYOUT_READY")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiscoveredCampaign(Base):
    """Campaigns scraped from the operator's logged-in Content Rewards session (extension)."""

    __tablename__ = "discovered_campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    external_id: Mapped[Optional[str]] = mapped_column(String(256), index=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(1024))
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(256))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cpm: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    budget_remaining_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    difficulty: Mapped[Optional[str]] = mapped_column(String(32))
    required_clips: Mapped[int] = mapped_column(Integer, default=3)
    min_duration_sec: Mapped[int] = mapped_column(Integer, default=15)
    max_duration_sec: Mapped[int] = mapped_column(Integer, default=60)
    opportunity_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    expected_profit: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    reject_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    operator_status: Mapped[str] = mapped_column(
        String(32), default="discovered"
    )  # discovered|top3|approved|rejected|collecting|producing|ready|posted|submitted|done
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id"))
    brief_text: Mapped[Optional[str]] = mapped_column(Text)
    asset_urls: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperatorNotification(Base):
    __tablename__ = "operator_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # review_required | revision | approved | payout_ready | submission_ready
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    action_url: Mapped[Optional[str]] = mapped_column(String(1024))
    action_label: Mapped[Optional[str]] = mapped_column(String(128))
    related_id: Mapped[Optional[str]] = mapped_column(String(36))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClipPerformance(Base):
    """Per-clip outcomes for the learning engine (record now, train after 50–100 clips)."""

    __tablename__ = "clip_performance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id"), index=True)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_accounts.id"), index=True)
    clip_version_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("clip_versions.id"))
    post_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("posts.id"))
    hook_type: Mapped[Optional[str]] = mapped_column(String(64))
    clip_length_band: Mapped[Optional[str]] = mapped_column(String(16))
    topic: Mapped[Optional[str]] = mapped_column(String(256))
    editing_style: Mapped[Optional[str]] = mapped_column(String(64))
    caption_style: Mapped[Optional[str]] = mapped_column(String(64))
    posting_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    approval_status: Mapped[Optional[str]] = mapped_column(String(64))
    verified_views: Mapped[int] = mapped_column(Integer, default=0)
    earnings: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductionEvent(Base):
    """Operator production queue timeline."""

    __tablename__ = "production_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id"))
    source_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("source_assets.id"))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="done")  # done | action_required | pending
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperatorSettings(Base):
    __tablename__ = "operator_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    monthly_target: Mapped[float] = mapped_column(Numeric(14, 2), default=1000)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_accounts(db: Session) -> None:
    if db.query(SocialAccount).count():
        return
    rows = [
        SocialAccount(
            platform="content_rewards",
            handle="operator",
            display_name="ClipOps CR Account",
            style=None,
            audience_geo=["US", "CA"],
            audience_notes="Single Content Rewards identity — never duplicate",
        ),
        SocialAccount(
            platform="tiktok",
            handle="tiktok_dramatic",
            display_name="TikTok 1 — Dramatic",
            style="dramatic",
            audience_geo=["US", "CA"],
            audience_notes="Fast, dramatic clips",
            preferred_clip_length="15-25",
            preferred_hooks=["drama", "question"],
        ),
        SocialAccount(
            platform="tiktok",
            handle="tiktok_educational",
            display_name="TikTok 2 — Educational",
            style="educational",
            audience_geo=["US", "CA"],
            audience_notes="Educational / storytelling",
            preferred_clip_length="25-40",
            preferred_hooks=["surprising_fact", "question"],
        ),
        SocialAccount(
            platform="tiktok",
            handle="tiktok_commentary",
            display_name="TikTok 3 — Commentary",
            style="commentary",
            audience_geo=["US", "CA"],
            audience_notes="Commentary, captions, reactions",
            preferred_clip_length="15-25",
            preferred_hooks=["controversy", "question"],
        ),
    ]
    db.add_all(rows)
    db.commit()


def seed_settings(db: Session) -> None:
    if db.query(OperatorSettings).count():
        return
    db.add(OperatorSettings(monthly_target=1000, currency="GBP"))
    db.commit()


def _sqlite_add_missing_columns() -> None:
    """Best-effort ALTER for local sqlite when models gain columns."""
    url = str(engine.url)
    if not url.startswith("sqlite"):
        return
    statements = [
        "ALTER TABLE social_accounts ADD COLUMN preferred_clip_length VARCHAR(16)",
        "ALTER TABLE social_accounts ADD COLUMN preferred_hooks JSON",
        "ALTER TABLE source_assets ADD COLUMN transcript_engine VARCHAR(32)",
        "ALTER TABLE clip_versions ADD COLUMN transcript_engine VARCHAR(32)",
        "ALTER TABLE clip_versions ADD COLUMN fabrication_override_reason TEXT",
    ]
    with engine.begin() as conn:
        for sql in statements:
            try:
                conn.exec_driver_sql(sql)
            except Exception:
                pass  # column already exists


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()
    db = SessionLocal()
    try:
        seed_accounts(db)
        seed_settings(db)
    finally:
        db.close()
