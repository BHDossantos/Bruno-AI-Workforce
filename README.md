# Bruno AI Workforce

A private AI workforce platform that runs daily workflows across six business
areas and produces a single executive brief every morning. You review, approve,
and execute — the agents do the sourcing, scoring, and drafting.

| # | Agent | Schedule | Daily output |
|---|-------|----------|--------------|
| 1 | Executive Job Hunter | 5 AM | 25 scored executive jobs + application artifacts |
| 2 | Insurance Lead Generator | 6 AM | 200 leads (100 commercial + 100 personal) |
| 3 | SavoryMind Growth | 7 AM | 100 restaurant prospects + 100 consumer targets |
| 4 | Music Marketing | 8 AM | 50 playlists, 25 influencers, daily content package |
| 5 | Instagram Growth | 9 AM | 100 target accounts + weekly content calendar |
| 6 | CEO Dashboard | 10 AM | 1 executive brief (emailed) |

> **Status:** Phase 1 MVP. All six agents are implemented and run end-to-end.
> **Live sourcing is wired**: jobs via the JSearch/Indeed aggregator (`JOBS_API_KEY`),
> commercial insurance + restaurant prospects via Apollo.io (`APOLLO_API_KEY`),
> and qualified insurance leads auto-pushed to HubSpot (`HUBSPOT_API_KEY`). Each
> live source falls back to (and is topped up with) synthetic data so the system
> always runs and hits its daily targets even without credentials. Remaining
> sources (music/Instagram) are synthetic. AI content is real when
> `OPENAI_API_KEY` is set. See [`backend/app/integrations/`](backend/app/integrations/).

## Architecture

```
Next.js + Tailwind (frontend)  ──HTTP──>  FastAPI (backend)
                                              │
                       ┌──────────────────────┼───────────────────────┐
                       │                       │                       │
                 PostgreSQL              APScheduler / n8n        OpenAI API
              (all data tables)        (daily cron triggers)   (content + scoring)
                                              │
                                       Integrations: HubSpot, Gmail,
                                       Apollo, Google Sheets/Drive
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env: set ADMIN_PASSWORD, and OPENAI_API_KEY for real AI output.
# Generate ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up --build
```

Then open:

- **Dashboard:** http://localhost:3000  (log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`)
- **API + docs:** http://localhost:8000/docs
- **n8n:** http://localhost:5678

To run all agents immediately (instead of waiting for the cron schedule), use the
**"Run all agents now"** button on the home dashboard, or:

```bash
# get a token
curl -s -X POST http://localhost:8000/auth/token \
  -d "username=$ADMIN_EMAIL&password=$ADMIN_PASSWORD" | jq -r .access_token
# run everything
curl -X POST http://localhost:8000/agents/run-all -H "Authorization: Bearer <token>"
```

## Local development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)   # or set DATABASE_URL to a local Postgres
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Project layout

```
backend/        FastAPI app, agents, models, AI prompts, integrations
  app/agents/   The six daily agents (one file each)
  app/ai/       OpenAI client wrapper + prompt library
  app/routers/  REST endpoints per dashboard page
  db/schema.sql Full PostgreSQL schema (reference)
frontend/       Next.js 14 (App Router) + Tailwind dashboard
n8n/workflows/  Importable daily-trigger workflow
docs/           Architecture + deployment guides
```

## Dashboard pages

Home · Jobs · Insurance Leads · SavoryMind Leads · Music Campaigns ·
Instagram Planner · Outbox · Daily Brief.

## Email (Gmail) — outbound + inbound

Outreach and the daily report are routed through **two Gmail accounts**:

| Account | Address (default) | Used by |
|---------|-------------------|---------|
| `personal` | `brunodossantos707@gmail.com` | all agents except insurance + the CEO report |
| `insurance` | `bruno@thrustinsurance.com` | the Insurance agent's outreach |

- **Outbound mode** (`GMAIL_OUTBOUND_MODE`): `send` (auto-send now, the current
  setting), `send_on_approve`, or `draft`. Safety guardrails always apply: a
  per-account daily cap (`GMAIL_DAILY_SEND_CAP`, default 50), no contacting the
  same address twice in a day, and a required recipient. Cold emails include
  unsubscribe language.
- **Inbound**: both mailboxes are polled every 2 hours (and on demand from the
  Outbox page) for replies, which flip the matching lead/restaurant/message to
  `Replied`.
- The **Outbox** page lists every outbound message, its sending account, and
  status; you can approve/send drafts and trigger a reply sync.

Set up each account's OAuth token once — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#gmail-oauth-setup).

## Marketing skills

`.claude/skills/` ships **45 marketing Agent Skills** (copywriting, cold email,
prospecting, SEO/AI SEO, paid ads, social, SMS, pricing, churn, referrals, PR,
and more) that Claude Code auto-discovers in this repo — use them to craft and
sharpen the messaging the agents generate. Vendored (MIT) from
[coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills);
see [`.claude/skills/README.md`](.claude/skills/README.md) for attribution.

## Security

- JWT auth with role-based access (`admin` / `operator` / `viewer`).
- Stored third-party API keys are encrypted at rest (Fernet).
- Every agent action is written to the `action_logs` audit table.
- **Nothing sends automatically** — messages are drafted with `approved=false`
  until a human approves them. Cold emails include unsubscribe language.

## Roadmap

- **Phase 1 (done):** DB, dashboard, Job/Insurance/SavoryMind agents, CEO report.
- **Phase 2:** Music + Instagram agents (also implemented), Gmail drafts,
  HubSpot push, Google Sheets export.
- **Phase 3:** Auto-send approved emails, reply classification, KPI charts,
  lead scoring tuning, A/B testing, calendar booking links.

## License

Private / proprietary.
