"""SQLAlchemy ORM models — mirror of backend/db/schema.sql."""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Canonical lead lifecycle statuses (kept as plain strings for portability).
LEAD_STATUSES = [
    "New", "Drafted", "Sent", "Opened", "Replied",
    "Interested", "Follow-up Needed", "Closed Won", "Closed Lost",
]


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    schedule_cron: Mapped[str | None] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(String, default="pending")
    summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    agent: Mapped["Agent"] = relationship(back_populates="tasks")


class ActionLog(Base):
    __tablename__ = "action_logs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    actor: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str | None] = mapped_column(String)
    website: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    size: Mapped[str | None] = mapped_column(String)
    linkedin: Mapped[str | None] = mapped_column(String)
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    full_name: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    linkedin: Mapped[str | None] = mapped_column(String)
    instagram: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="New")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str | None] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    resume_match: Mapped[str | None] = mapped_column(Text)
    cover_letter: Mapped[str | None] = mapped_column(Text)
    recruiter_msg: Mapped[str | None] = mapped_column(Text)
    hiring_msg: Mapped[str | None] = mapped_column(Text)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, default="New")
    notes: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[uuid.UUID] = _uuid_pk()
    segment: Mapped[str] = mapped_column(String, nullable=False)  # commercial | personal
    category: Mapped[str | None] = mapped_column(String)
    company_name: Mapped[str | None] = mapped_column(String)
    owner_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    website: Mapped[str | None] = mapped_column(String)
    linkedin: Mapped[str | None] = mapped_column(String)
    industry: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="New", index=True)
    cold_email: Mapped[str | None] = mapped_column(Text)
    call_script: Mapped[str | None] = mapped_column(Text)
    linkedin_msg: Mapped[str | None] = mapped_column(Text)
    pushed_to_crm: Mapped[bool] = mapped_column(Boolean, default=False)
    times_contacted: Mapped[int] = mapped_column(Integer, default=0)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Restaurant(Base):
    __tablename__ = "restaurants"
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String, default="prospect")  # prospect | consumer
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_manager: Mapped[str | None] = mapped_column(String)
    website: Mapped[str | None] = mapped_column(String)
    menu_url: Mapped[str | None] = mapped_column(String)
    instagram: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    cuisine: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    pain_points: Mapped[str | None] = mapped_column(Text)
    menu_analysis: Mapped[dict | None] = mapped_column(JSONB)
    pitch_email: Mapped[str | None] = mapped_column(Text)
    linkedin_msg: Mapped[str | None] = mapped_column(Text)
    follow_up: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="New")
    times_contacted: Mapped[int] = mapped_column(Integer, default=0)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MusicPlaylist(Base):
    __tablename__ = "music_playlists"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    curator_name: Mapped[str | None] = mapped_column(String)
    genre: Mapped[str | None] = mapped_column(String)
    submission_link: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    instagram: Mapped[str | None] = mapped_column(String)
    followers: Mapped[int | None] = mapped_column(Integer)
    genre_match: Mapped[int] = mapped_column(Integer, default=0)
    pitch: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="New")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Influencer(Base):
    __tablename__ = "influencers"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    niche: Mapped[str | None] = mapped_column(String)
    platform: Mapped[str | None] = mapped_column(String)
    handle: Mapped[str | None] = mapped_column(String)
    followers: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(String)
    dm_pitch: Mapped[str | None] = mapped_column(Text)
    collab_pitch: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="New")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InstagramTarget(Base):
    __tablename__ = "instagram_targets"
    id: Mapped[uuid.UUID] = _uuid_pk()
    handle: Mapped[str] = mapped_column(String, nullable=False)
    niche: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    followers: Mapped[int | None] = mapped_column(Integer)
    comment_idea: Mapped[str | None] = mapped_column(Text)
    dm_opener: Mapped[str | None] = mapped_column(Text)
    story_reply: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="New")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[uuid.UUID] = _uuid_pk()
    channel: Mapped[str | None] = mapped_column(String)  # music | instagram
    title: Mapped[str | None] = mapped_column(String)
    content: Mapped[dict | None] = mapped_column(JSONB)
    scheduled_for: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _uuid_pk()
    channel: Mapped[str | None] = mapped_column(String)
    direction: Mapped[str] = mapped_column(String, default="outbound")
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_email: Mapped[str | None] = mapped_column(String, index=True)
    from_account: Mapped[str] = mapped_column(String, default="personal")  # personal | insurance
    subject: Mapped[str | None] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="Drafted")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_id: Mapped[str | None] = mapped_column(String)  # Gmail message/draft id
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_ups"
    id: Mapped[uuid.UUID] = _uuid_pk()
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyReport(Base):
    __tablename__ = "daily_reports"
    id: Mapped[uuid.UUID] = _uuid_pk()
    report_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    summary: Mapped[str | None] = mapped_column(Text)
    top_actions: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KpiMetric(Base):
    __tablename__ = "kpi_metrics"
    id: Mapped[uuid.UUID] = _uuid_pk()
    metric_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Connection(Base):
    """A user-connected app / social / ad / commerce account.

    Credentials are stored as an encrypted JSON blob (Fernet). The platform reads
    a connection's declared capabilities (from the provider registry) to build and
    run its marketing & sales funnel automatically.
    """
    __tablename__ = "connections"
    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)  # registry key
    display_name: Mapped[str] = mapped_column(String, nullable=False)  # user's label
    account_ref: Mapped[str | None] = mapped_column(String)  # handle / email / account id
    credentials_enc: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted JSON
    status: Mapped[str] = mapped_column(String, default="connected")  # connected|error|disconnected
    funnel_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    goal: Mapped[str | None] = mapped_column(String)  # leads | sales | followers | bookings
    settings: Mapped[dict | None] = mapped_column(JSONB)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandProfile(Base):
    """Single-row profile of the user's brand/account that tailors ALL AI content
    (Instagram calendar, music package, outreach tone). Editable in the UI."""
    __tablename__ = "brand_profile"
    id: Mapped[uuid.UUID] = _uuid_pk()
    business_name: Mapped[str | None] = mapped_column(String)
    niche: Mapped[str | None] = mapped_column(String)        # what you do / industry
    location: Mapped[str | None] = mapped_column(String)
    audience: Mapped[str | None] = mapped_column(String)     # who you target
    value_prop: Mapped[str | None] = mapped_column(Text)     # your offer / differentiator
    website: Mapped[str | None] = mapped_column(String)
    tone: Mapped[str | None] = mapped_column(String)         # brand voice
    instagram_handle: Mapped[str | None] = mapped_column(String)
    content_pillars: Mapped[str | None] = mapped_column(Text)  # comma-separated themes
    music_artist: Mapped[str | None] = mapped_column(String)
    music_genres: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionState(Base):
    """State overlay for the Daily-Brief actions (which are derived live).

    Keyed by a deterministic action key (e.g. 'follow_up:lead:<id>') so an
    executed/dismissed action stays out of the brief without a full action table.
    """
    __tablename__ = "action_states"
    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open|done|dismissed
    result: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Memory(Base):
    """The AI memory / knowledge graph: one fact Bruno's workforce should remember
    (about a person, company, lead, preference, goal, or event). Embeddings are
    stored as a float array (JSONB) and cosine-ranked in Python — no vector
    extension or extra server needed; swappable to Mem0/pgvector at scale."""
    __tablename__ = "memories"
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String, default="fact", index=True)  # fact|contact|preference|goal|event|note
    subject: Mapped[str | None] = mapped_column(String, index=True)        # who/what it's about
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSONB)                  # float[]; null when offline
    meta: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(String)                     # agent/user/import
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Objective(Base):
    """An OUTCOME Bruno is driving toward (not a project). Agents/sources feed it,
    and its weight ranks how much attention its actions get in the Daily Brief."""
    __tablename__ = "objectives"
    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    command_center: Mapped[str] = mapped_column(String, nullable=False, index=True)
    metric: Mapped[str | None] = mapped_column(String)        # income | revenue | followers ...
    target_value: Mapped[float | None] = mapped_column(Numeric)
    current_value: Mapped[float] = mapped_column(Numeric, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=100)
    weight: Mapped[float] = mapped_column(Numeric, default=0.5)  # 0–1, scales priority
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
