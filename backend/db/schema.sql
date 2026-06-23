-- ============================================================================
-- Bruno AI Workforce — PostgreSQL schema
-- This file documents the full data model. The application also creates these
-- tables automatically from the SQLAlchemy models (see backend/app/models.py),
-- so running it manually is optional but useful for review / bare-metal setups.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Shared lead lifecycle status used across leads / contacts / applications.
DO $$ BEGIN
    CREATE TYPE lead_status AS ENUM (
        'New', 'Drafted', 'Sent', 'Opened', 'Replied',
        'Interested', 'Follow-up Needed', 'Closed Won', 'Closed Lost'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── Identity & access ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    full_name       TEXT,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'admin',        -- admin | operator | viewer
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agents & tasks ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key           TEXT UNIQUE NOT NULL,                   -- job_hunter, insurance, ...
    name          TEXT NOT NULL,
    description   TEXT,
    schedule_cron TEXT,                                   -- e.g. '0 5 * * *'
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    UUID REFERENCES agents(id) ON DELETE SET NULL,
    status      TEXT NOT NULL DEFAULT 'pending',          -- pending|running|success|error
    summary     TEXT,
    payload     JSONB,
    error       TEXT,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log: every agent action / system event for security & traceability.
CREATE TABLE IF NOT EXISTS action_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor      TEXT,                                       -- agent key or user email
    action     TEXT NOT NULL,
    entity     TEXT,
    entity_id  TEXT,
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Company / contact graph (shared by insurance + savorymind + music) ──────
CREATE TABLE IF NOT EXISTS companies (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    industry   TEXT,
    website    TEXT,
    city       TEXT,
    size       TEXT,
    linkedin   TEXT,
    metadata   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contacts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  UUID REFERENCES companies(id) ON DELETE SET NULL,
    full_name   TEXT,
    title       TEXT,
    email       TEXT,
    phone       TEXT,
    linkedin    TEXT,
    instagram   TEXT,
    status      lead_status NOT NULL DEFAULT 'New',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent 1: Executive Job Hunter ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    company         TEXT,
    location        TEXT,
    remote          BOOLEAN DEFAULT FALSE,
    salary_min      INTEGER,
    salary_max      INTEGER,
    source          TEXT,                                  -- linkedin | indeed | ...
    url             TEXT,
    description     TEXT,
    score           INTEGER DEFAULT 0,
    score_breakdown JSONB,
    resume_match    TEXT,
    cover_letter    TEXT,
    recruiter_msg   TEXT,
    hiring_msg      TEXT,
    found_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS applications (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID REFERENCES jobs(id) ON DELETE CASCADE,
    status     lead_status NOT NULL DEFAULT 'New',
    notes      TEXT,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent 2: Insurance Lead Generator ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    segment       TEXT NOT NULL,                           -- commercial | personal
    category      TEXT,                                    -- contractor, homeowner, ...
    company_name  TEXT,
    owner_name    TEXT,
    email         TEXT,
    phone         TEXT,
    website       TEXT,
    linkedin      TEXT,
    industry      TEXT,
    reason        TEXT,                                    -- why they may need insurance
    score         INTEGER DEFAULT 0,
    status        lead_status NOT NULL DEFAULT 'New',
    cold_email    TEXT,
    call_script   TEXT,
    linkedin_msg  TEXT,
    pushed_to_crm BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent 3: SavoryMind Growth ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS restaurants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            TEXT NOT NULL DEFAULT 'prospect',      -- prospect | consumer
    name            TEXT NOT NULL,
    owner_manager   TEXT,
    website         TEXT,
    menu_url        TEXT,
    instagram       TEXT,
    email           TEXT,
    phone           TEXT,
    cuisine         TEXT,
    city            TEXT,
    pain_points     TEXT,
    menu_analysis   JSONB,                                 -- upsell / optimization / pairing / reputation
    pitch_email     TEXT,
    linkedin_msg    TEXT,
    follow_up       TEXT,
    status          lead_status NOT NULL DEFAULT 'New',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent 4: Music Marketing ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS music_playlists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    curator_name    TEXT,
    genre           TEXT,
    submission_link TEXT,
    email           TEXT,
    instagram       TEXT,
    followers       INTEGER,
    genre_match     INTEGER DEFAULT 0,
    pitch           TEXT,
    status          lead_status NOT NULL DEFAULT 'New',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS influencers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    niche       TEXT,                                      -- music reviewer, dance, romance ...
    platform    TEXT,
    handle      TEXT,
    followers   INTEGER,
    email       TEXT,
    dm_pitch    TEXT,
    collab_pitch TEXT,
    status      lead_status NOT NULL DEFAULT 'New',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent 5: Instagram Growth ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS instagram_targets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle      TEXT NOT NULL,
    niche       TEXT,                                      -- rome lifestyle, jiu-jitsu ...
    category    TEXT,                                      -- follower|collaborator|customer|fan|business
    followers   INTEGER,
    comment_idea TEXT,
    dm_opener   TEXT,
    story_reply TEXT,
    status      lead_status NOT NULL DEFAULT 'New',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Campaigns / content (shared by music + instagram) ───────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel     TEXT,                                      -- music | instagram
    title       TEXT,
    content     JSONB,                                     -- reels, captions, hashtags, calendar
    scheduled_for DATE,
    status      TEXT NOT NULL DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Outreach: messages + follow-up sequences ────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel      TEXT,                                     -- email | linkedin | dm | call
    direction    TEXT NOT NULL DEFAULT 'outbound',
    entity_type  TEXT,                                     -- lead | restaurant | job | contact ...
    entity_id    UUID,
    subject      TEXT,
    body         TEXT,
    status       lead_status NOT NULL DEFAULT 'Drafted',
    approved     BOOLEAN NOT NULL DEFAULT FALSE,           -- nothing sends until approved
    sent_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type  TEXT,
    entity_id    UUID,
    step         INTEGER NOT NULL,                         -- 0,1,2,3,4
    due_date     DATE NOT NULL,
    body         TEXT,
    completed    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent 6: CEO Dashboard / reporting ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date DATE NOT NULL DEFAULT CURRENT_DATE,
    summary     TEXT,
    top_actions JSONB,
    metrics     JSONB,
    emailed     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kpi_metrics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,
    name        TEXT NOT NULL,
    value       NUMERIC,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Helpful indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_score        ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_status      ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_segment     ON leads(segment);
CREATE INDEX IF NOT EXISTS idx_restaurants_kind  ON restaurants(kind);
CREATE INDEX IF NOT EXISTS idx_followups_due     ON follow_ups(due_date) WHERE completed = FALSE;
CREATE INDEX IF NOT EXISTS idx_reports_date      ON daily_reports(report_date DESC);
