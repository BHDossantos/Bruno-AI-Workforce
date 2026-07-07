"""Pydantic response/request schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, computed_field

from .insurance_lines import line_for as _line_for
from .lead_temperature import classify as _temperature


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ─────────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool


# ── Agents ───────────────────────────────────────────────────────────────────
class AgentOut(ORMModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    schedule_cron: str | None = None
    enabled: bool
    last_run_at: datetime | None = None


class JobOut(ORMModel):
    id: uuid.UUID
    title: str
    company: str | None = None
    location: str | None = None
    remote: bool
    salary_min: int | None = None
    salary_max: int | None = None
    source: str | None = None
    url: str | None = None
    score: int
    score_breakdown: dict | None = None
    resume_match: str | None = None
    cover_letter: str | None = None
    recruiter_msg: str | None = None
    hiring_msg: str | None = None
    found_at: datetime


class LeadOut(ORMModel):
    id: uuid.UUID
    segment: str
    category: str | None = None
    company_name: str | None = None
    owner_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    linkedin: str | None = None
    industry: str | None = None
    reason: str | None = None
    score: int
    status: str
    cold_email: str | None = None
    call_script: str | None = None
    linkedin_msg: str | None = None
    pushed_to_crm: bool
    times_contacted: int = 0
    last_contacted_at: datetime | None = None
    created_at: datetime

    @computed_field
    @property
    def temperature(self) -> str:
        # Pass score so in-market inbound leads (EverQuote) read HOT by source.
        return _temperature(self.status, self.score)

    @computed_field
    @property
    def fit_score(self) -> int:
        from .lead_fit import score
        return score(self)

    @computed_field
    @property
    def line(self) -> str:
        """Insurance line of business: home / auto / life / commercial."""
        return _line_for(self.category, self.segment, self.industry)


class RestaurantOut(ORMModel):
    id: uuid.UUID
    kind: str
    name: str
    owner_manager: str | None = None
    website: str | None = None
    menu_url: str | None = None
    instagram: str | None = None
    email: str | None = None
    phone: str | None = None
    cuisine: str | None = None
    city: str | None = None
    pain_points: str | None = None
    menu_analysis: dict | None = None
    pitch_email: str | None = None
    linkedin_msg: str | None = None
    follow_up: str | None = None
    status: str
    times_contacted: int = 0
    last_contacted_at: datetime | None = None
    created_at: datetime

    @computed_field
    @property
    def temperature(self) -> str:
        return _temperature(self.status)

    @computed_field
    @property
    def fit_score(self) -> int:
        from .restaurant_fit import score
        return score(self)


class PlaylistOut(ORMModel):
    id: uuid.UUID
    name: str
    curator_name: str | None = None
    genre: str | None = None
    submission_link: str | None = None
    email: str | None = None
    instagram: str | None = None
    followers: int | None = None
    genre_match: int
    pitch: str | None = None
    status: str


class InfluencerOut(ORMModel):
    id: uuid.UUID
    name: str
    niche: str | None = None
    platform: str | None = None
    handle: str | None = None
    followers: int | None = None
    email: str | None = None
    dm_pitch: str | None = None
    collab_pitch: str | None = None
    status: str


class MusicReleaseCreate(BaseModel):
    title: str
    era: str | None = None
    release_date: date | None = None
    city: str | None = None
    story: str | None = None
    key_line: str | None = None
    language: str | None = None


class MusicReleaseOut(ORMModel):
    id: uuid.UUID
    title: str
    era: str | None = None
    release_date: date | None = None
    city: str | None = None
    story: str | None = None
    key_line: str | None = None
    language: str | None = None
    status: str


class ReleasePieceOut(ORMModel):
    id: uuid.UUID
    topic: str
    channel: str
    title: str | None = None
    body: str | None = None
    hashtags: str | None = None
    status: str
    meta: dict | None = None


class InstagramTargetOut(ORMModel):
    id: uuid.UUID
    handle: str
    niche: str | None = None
    category: str | None = None
    followers: int | None = None
    comment_idea: str | None = None
    dm_opener: str | None = None
    story_reply: str | None = None
    status: str


class CampaignOut(ORMModel):
    id: uuid.UUID
    channel: str | None = None
    title: str | None = None
    content: dict | None = None
    scheduled_for: date | None = None
    status: str


class ReportOut(ORMModel):
    id: uuid.UUID
    report_date: date
    summary: str | None = None
    top_actions: dict | None = None
    metrics: dict | None = None
    emailed: bool


class StatusUpdate(BaseModel):
    status: str


class MessageOut(ORMModel):
    id: uuid.UUID
    channel: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    to_email: str | None = None
    from_account: str
    subject: str | None = None
    body: str | None = None
    status: str
    approved: bool
    provider_id: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


# ── Connections (connect-any-account platform) ───────────────────────────────
class ConnectionCreate(BaseModel):
    provider: str
    display_name: str | None = None
    account_ref: str | None = None
    goal: str | None = None
    credentials: dict[str, str] = {}
    settings: dict | None = None


class ConnectionOut(ORMModel):
    id: uuid.UUID
    provider: str
    display_name: str
    account_ref: str | None = None
    status: str
    funnel_enabled: bool
    goal: str | None = None
    settings: dict | None = None
    last_synced_at: datetime | None = None
    created_at: datetime


class ConnectionUpdate(BaseModel):
    display_name: str | None = None
    goal: str | None = None
    funnel_enabled: bool | None = None
    credentials: dict[str, str] | None = None
    settings: dict | None = None


# ── Brand profile (tailors all AI content to the user's account) ──────────────
class BrandProfileOut(ORMModel):
    id: uuid.UUID
    business_name: str | None = None
    niche: str | None = None
    location: str | None = None
    audience: str | None = None
    value_prop: str | None = None
    website: str | None = None
    tone: str | None = None
    instagram_handle: str | None = None
    content_pillars: str | None = None
    music_artist: str | None = None
    music_genres: str | None = None
    music_links: str | None = None


class BrandProfileUpdate(BaseModel):
    business_name: str | None = None
    niche: str | None = None
    location: str | None = None
    audience: str | None = None
    value_prop: str | None = None
    website: str | None = None
    tone: str | None = None
    instagram_handle: str | None = None
    content_pillars: str | None = None
    music_artist: str | None = None
    music_genres: str | None = None
    music_links: str | None = None
