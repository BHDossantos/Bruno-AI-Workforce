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


class Relationship(Base):
    """An edge in the relationship graph — links two entities (by their memory
    subject, e.g. a name) so the AI reasons across connections rather than isolated
    rows: recruiter → company → hiring manager → interview, 'referred by', etc."""
    __tablename__ = "relationships"
    id: Mapped[uuid.UUID] = _uuid_pk()
    from_subject: Mapped[str] = mapped_column(String, index=True, nullable=False)
    from_type: Mapped[str | None] = mapped_column(String)
    to_subject: Mapped[str] = mapped_column(String, index=True, nullable=False)
    to_type: Mapped[str | None] = mapped_column(String)
    relation: Mapped[str] = mapped_column(String, nullable=False)  # works_at|hiring_manager_for|referred_by|introduced_by|colleague|…
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsletterSubscriber(Base):
    """A warm reply auto-subscribed to a funnel's newsletter. Only people who
    replied are added (CAN-SPAM friendly); each has a token for one-click
    unsubscribe."""
    __tablename__ = "newsletter_subscribers"
    id: Mapped[uuid.UUID] = _uuid_pk()
    funnel: Mapped[str] = mapped_column(String, index=True)  # insurance|bnbglobal|savorymind|music
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    token: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsletterSend(Base):
    """A record of one newsletter issue sent to a funnel's list (for tracking)."""
    __tablename__ = "newsletter_sends"
    id: Mapped[uuid.UUID] = _uuid_pk()
    funnel: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str | None] = mapped_column(String)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsletterDraft(Base):
    """An AI-written newsletter issue, stored so it's visible and reviewable before
    it goes out. status: draft (written, awaiting you) | sent | dismissed."""
    __tablename__ = "newsletter_drafts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    funnel: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str | None] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Decision(Base):
    """A logged major decision — what was decided, the reasoning, the expected
    outcome and confidence — later marked with the ACTUAL outcome. Over time the
    journal surfaces patterns (win-rate by category/confidence) so the workforce
    learns how Bruno decides and can calibrate its own recommendations."""
    __tablename__ = "decisions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, index=True)  # career|business|insurance|music|financial|personal|other
    decision: Mapped[str | None] = mapped_column(Text)            # what was decided
    reasoning: Mapped[str | None] = mapped_column(Text)           # why
    expected_outcome: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(Integer, default=50)  # 0..100 at decision time
    status: Mapped[str] = mapped_column(String, default="Open", index=True)  # Open|Reviewed
    outcome: Mapped[str | None] = mapped_column(String)           # success|failure|mixed
    outcome_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommanderOrder(Base):
    """A direct order the user gives a Commander from the Command Centers page —
    optionally with a target amount. Stored for the record and executed (the
    commander runs its agents now). Lets the user 'pick the amount and give them
    orders' instead of only watching."""
    __tablename__ = "commander_orders"
    id: Mapped[uuid.UUID] = _uuid_pk()
    center: Mapped[str] = mapped_column(String, index=True)  # wealth|business|influence|life_ops
    order: Mapped[str | None] = mapped_column(Text)          # free-text instruction
    amount: Mapped[float | None] = mapped_column(Numeric)    # optional target amount
    status: Mapped[str] = mapped_column(String, default="received")  # received|run|failed
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Opportunity(Base):
    """Any scored opportunity — investor, podcast, collab, speaking slot, brand
    deal, partnership, press. Makes EVERYTHING comparable on one economics formula
    (value × probability ÷ effort × objective_weight × urgency) so it ranks into
    the same daily brief as jobs and leads."""
    __tablename__ = "opportunities"
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String, index=True)  # investor|podcast|collab|speaking|partnership|brand_deal|press|conference|other
    title: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)       # expected $ value
    probability: Mapped[float] = mapped_column(Numeric(4, 3), default=0.3)  # 0..1
    urgency: Mapped[float] = mapped_column(Numeric(4, 2), default=1.0)
    effort: Mapped[int] = mapped_column(Integer, default=2)
    objective: Mapped[str | None] = mapped_column(String)   # maps to objective weights
    command_center: Mapped[str] = mapped_column(String, default="business")
    status: Mapped[str] = mapped_column(String, default="Open", index=True)  # Open|Won|Lost|Dismissed
    link: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
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


class MusicRelease(Base):
    """A song/single release in the Bruno D era strategy. One release fans out
    into a full content kit (music video, lyric video, sax/acoustic/piano versions,
    behind-the-song, the repeatable TikTok line, reel cuts) on a 4-week cadence."""
    __tablename__ = "music_releases"
    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)      # the song
    era: Mapped[str | None] = mapped_column(String)                # which era it belongs to
    release_date: Mapped[date | None] = mapped_column(Date)        # drives the cadence
    city: Mapped[str | None] = mapped_column(String)               # story location (Rome/Naples/…)
    story: Mapped[str | None] = mapped_column(Text)                # the real story behind it
    key_line: Mapped[str | None] = mapped_column(String)           # the one repeatable line
    language: Mapped[str | None] = mapped_column(String)           # EN / ES / PT / mix
    status: Mapped[str] = mapped_column(String, default="Planned")  # Planned|Kit Built|Released
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
    music_links: Mapped[str | None] = mapped_column(Text)  # streaming/follow links for fan CTAs
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    """A financial account or holding. Net worth = assets − liabilities."""
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="asset")        # asset|liability
    category: Mapped[str | None] = mapped_column(String)             # checking|savings|investment|credit|loan|cash|property
    balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String, default="USD")
    institution: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="manual")    # manual|plaid|import
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """A money movement. amount > 0 = income, amount < 0 = expense."""
    __tablename__ = "transactions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    category: Mapped[str | None] = mapped_column(String, index=True)
    description: Mapped[str | None] = mapped_column(String)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    source: Mapped[str] = mapped_column(String, default="manual")    # manual|csv|plaid
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentItem(Base):
    """One piece of channel-ready content from the Content Factory, and the
    content-memory record (with an embedding for 'have we covered this?' dedup).
    Status: generated → needs_approval → scheduled → published (per approval mode)."""
    __tablename__ = "content_items"
    id: Mapped[uuid.UUID] = _uuid_pk()
    topic: Mapped[str] = mapped_column(String, index=True)
    business: Mapped[str | None] = mapped_column(String, index=True)   # executive|insurance|savorymind|music|bnbglobal|personal
    channel: Mapped[str] = mapped_column(String, index=True)           # linkedin|instagram|tiktok|youtube|x|facebook|blog|email|podcast
    title: Mapped[str | None] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="generated", index=True)
    embedding: Mapped[list | None] = mapped_column(JSONB)              # topic embedding for dedup
    meta: Mapped[dict | None] = mapped_column(JSONB)                   # views/likes/etc + result
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialSnapshot(Base):
    """A point-in-time follower/reach reading per platform, for growth charts."""
    __tablename__ = "social_snapshots"
    id: Mapped[uuid.UUID] = _uuid_pk()
    platform: Mapped[str] = mapped_column(String, index=True)
    followers: Mapped[int | None] = mapped_column(Integer)
    reach: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrowserTask(Base):
    """A browser-worker job — e.g. fill a job application form. Holds the prepared
    field map and the run result. Status: prepared → running → needs_review →
    submitted (or failed). Never auto-submits unless explicitly configured."""
    __tablename__ = "browser_tasks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String, default="job_application")
    target_url: Mapped[str | None] = mapped_column(String)
    entity_type: Mapped[str | None] = mapped_column(String)  # e.g. "job"
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String, default="prepared", index=True)
    mode: Mapped[str | None] = mapped_column(String)  # assist|automation
    field_map: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManualContact(Base):
    """A standalone contact (recruiter, advisor, partner) not owned by an agent
    source. Source entities (leads, restaurants, jobs, curators) surface through
    the CRM aggregation; this table holds the people you add by hand."""
    __tablename__ = "manual_contacts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, index=True)
    phone: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="contact")  # recruiter|advisor|partner|...
    status: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


class Grant(Base):
    """A funding opportunity sourced by the Foundation's Grant Research agent —
    scored by how well it fits the foundation's mission/pillars."""
    __tablename__ = "grants"
    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)
    funder: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String, index=True)  # grants_gov | curated | …
    external_id: Mapped[str | None] = mapped_column(String, index=True)  # dedupe key
    url: Mapped[str | None] = mapped_column(String)
    amount: Mapped[float | None] = mapped_column(Numeric)
    deadline: Mapped[date | None] = mapped_column(Date)
    eligibility: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String)  # matched pillar
    summary: Mapped[str | None] = mapped_column(Text)
    match_score: Mapped[int] = mapped_column(Integer, default=0)  # 0–100 mission fit
    status: Mapped[str] = mapped_column(String, default="New", index=True)  # New|Reviewing|Applying|Submitted|Won|Lost|Skipped
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentBlueprint(Base):
    """An AI sales agent generated from a business URL — the offer, ICP, target
    industries, pain points, outreach angles and message scripts the agent uses.
    (Instantly/Smartlead 'Create Agent from URL'.)"""
    __tablename__ = "agent_blueprints"
    id: Mapped[uuid.UUID] = _uuid_pk()
    url: Mapped[str] = mapped_column(String, nullable=False)
    business: Mapped[str | None] = mapped_column(String)
    offer: Mapped[str | None] = mapped_column(Text)
    icp: Mapped[str | None] = mapped_column(Text)
    industries: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[str | None] = mapped_column(Text)
    angles: Mapped[str | None] = mapped_column(Text)
    scripts: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String, default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignPlan(Base):
    """A campaign generated from a natural-language brief ("find Boston restaurants
    under 4.3 stars and pitch SavoryMind, follow up 6×") — parsed into a structured
    plan the user can review and launch. (Instantly/Smartlead NL campaign builder.)"""
    __tablename__ = "campaign_plans"
    id: Mapped[uuid.UUID] = _uuid_pk()
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    business: Mapped[str | None] = mapped_column(String)
    agent_key: Mapped[str | None] = mapped_column(String)   # which agent runs it
    plan: Mapped[dict | None] = mapped_column(JSONB)        # audience, filters, sequence, schedule
    status: Mapped[str] = mapped_column(String, default="planned")  # planned|launched
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    """A WON insurance client — the book of business (post-sale CRM record).

    Tracks who they are, what they bought (carrier + line + premium), when it
    started and renews, and their communication history (via ClientNote). This is
    the true-CRM layer that lives after a lead converts."""
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # origin lead, if any
    # Which business this client belongs to (insurance | bnb | savorymind | music | …).
    business: Mapped[str] = mapped_column(String, default="insurance", index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, index=True)
    phone: Mapped[str | None] = mapped_column(String)
    # Address
    address: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)   # MA | NH | FL
    zip: Mapped[str | None] = mapped_column(String)
    # Policy
    line: Mapped[str | None] = mapped_column(String)     # auto | home | life | commercial
    carrier: Mapped[str | None] = mapped_column(String)  # Progressive, GEICO, State Farm, …
    policy_number: Mapped[str | None] = mapped_column(String)
    premium_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2))
    quote_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))
    services: Mapped[str | None] = mapped_column(Text)   # coverage / services on the policy
    status: Mapped[str] = mapped_column(String, default="Active")  # Active|Lapsed|Renewed|Cancelled
    signed_at: Mapped[date | None] = mapped_column(Date)      # when they signed up
    expires_at: Mapped[date | None] = mapped_column(Date)     # policy expiration / renewal
    notes: Mapped[str | None] = mapped_column(Text)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ClientNote(Base):
    """A timeline entry on a client — a call, email, SMS, meeting or note. The
    communication history + last-contact for the CRM record."""
    __tablename__ = "client_notes"
    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="note")  # note|call|email|sms|meeting
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Webhook(Base):
    """An outbound webhook subscription — notifies external automation tools
    (n8n, Make, Zapier, or anything that accepts a POST) when a subscribed event
    happens in Bruno, so custom automations can be built outside the app without
    a bespoke integration for every tool."""
    __tablename__ = "webhooks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    secret: Mapped[str | None] = mapped_column(String)  # HMAC-signs the payload when set
    events: Mapped[list] = mapped_column(JSONB, default=list)  # event keys, or ["*"] for all
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    """Runtime key/value settings that change without a redeploy — e.g. the global
    'agents_paused' kill-switch behind the Emergency Stop button."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
