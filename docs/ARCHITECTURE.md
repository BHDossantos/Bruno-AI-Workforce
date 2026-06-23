# Architecture

## Components

- **Frontend** — Next.js 14 (App Router) + Tailwind. Token-based auth stored in
  `localStorage`; every page is wrapped in `AuthGate`. One page per dashboard area.
- **Backend** — FastAPI + SQLAlchemy 2.0 + PostgreSQL. Boots via a `lifespan`
  hook that seeds the admin user/agents and starts the scheduler.
- **Scheduler** — APScheduler `BackgroundScheduler` registers each agent on its
  cron (5–10 AM). `n8n` can drive the same `/agents/{key}/run` endpoint instead.
- **AI** — `app/ai/client.py` wraps OpenAI chat completions with a JSON mode and
  an offline stub fallback. Prompts live in `app/ai/prompts.py`.
- **Integrations** — `app/integrations/` holds prospect data providers (synthetic
  today, with `TODO` hooks for live APIs), the HubSpot CRM push, and the SMTP mailer.

## Agent lifecycle

Each agent subclasses `BaseAgent` (`app/agents/base.py`):

1. `run()` records a `Task` row, calls `execute()`, captures success/error, and
   writes an `action_logs` entry. Always commits or rolls back cleanly.
2. `execute()` (per-agent) sources prospects → scores → calls OpenAI to draft
   content → persists rows → schedules the Day 0/2/5/10/20 follow-up sequence.

```
BaseAgent.run()
  ├─ touch agents.last_run_at
  ├─ Task(status=running)
  ├─ execute()  ← agent-specific
  │     ├─ providers.fetch_*()        # source
  │     ├─ score_*()                  # rank
  │     ├─ client.complete_json(...)  # draft (email/script/pitch)
  │     ├─ db.add(...)                # persist
  │     └─ schedule_follow_ups(...)   # cadence
  └─ Task(status=success|error) + action_logs
```

## Data model

See [`backend/db/schema.sql`](../backend/db/schema.sql) and
[`backend/app/models.py`](../backend/app/models.py). Tables: `users`, `agents`,
`tasks`, `action_logs`, `companies`, `contacts`, `jobs`, `applications`, `leads`,
`restaurants`, `music_playlists`, `influencers`, `instagram_targets`,
`campaigns`, `messages`, `follow_ups`, `daily_reports`, `kpi_metrics`.

The SQLAlchemy models create tables automatically on boot (`init_db`), so the
`schema.sql` file is for reference / bare-metal provisioning.

## Scoring rules

- **Jobs** (`job_hunter.py`): Remote +25, salary ≥ $200k +25, leadership +20,
  cloud/SRE +20, AI/data +10. Saved when ≥ 70; top 25 kept.
- **Insurance** (`insurance.py`): base 40 + contactability/segment signals.
  Leads ≥ 60 are pushed to HubSpot.
- **Music** (`music.py`): genre-match 100 when in the artist's target genres.

## Automation rules

- Lead statuses: New → Drafted → Sent → Opened → Replied → Interested →
  Follow-up Needed → Closed Won / Closed Lost.
- Follow-up cadence: Day 0, 2, 5, 10, 20 (`FOLLOW_UP_DAYS` in `base.py`).
- No message sends until `messages.approved = true`. Cold emails carry
  unsubscribe language (enforced in prompts).

## Where to plug in live data

Replace the synthetic generators in `app/integrations/providers.py`:

| Function | Live source |
|----------|-------------|
| `fetch_jobs` | Indeed MCP / LinkedIn / Wellfound / company careers |
| `fetch_insurance_leads` | Apollo.io / Windsor (HubSpot) |
| `fetch_restaurants` | Google Maps / Yelp |
| `fetch_playlists` / `fetch_influencers` | Spotify / SubmitHub / IG |
| `fetch_instagram_targets` | Instagram (manual export or API) |
