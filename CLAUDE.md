# Bruno AI Workforce — repo guide

AI-run growth/CRM platform: finds leads, drafts and sends email/SMS, places
calls, and logs structured conversation outcomes — across several businesses.

- **Backend**: FastAPI + SQLAlchemy + Postgres — `backend/app`
- **Frontend**: Next.js + TypeScript + Tailwind — `frontend`
- **Deploy**: GitHub Actions → Google Cloud Run + Cloud SQL

## Run the checks

```bash
# Backend tests (run from backend/)
DATABASE_URL="postgresql+psycopg://bruno:bruno@localhost:5432/bruno_ai" python -m pytest -q
# Frontend typecheck (run from frontend/)
npx tsc --noEmit
```

Some tests share DB state and can fail alone but pass in the full suite — judge a
new failure against the full-suite baseline and confirm it isn't pre-existing on
the base branch.

## Invariants you must not break

- **No migrations.** `create_all()` creates NEW tables only — it never ALTERs
  existing ones. New table = safe. New column on an existing table = NOT applied
  in prod automatically; use a new table or an explicit idempotent migration and
  flag it loudly.
- **Cloud Run startup probe.** The port must open fast. All boot work (seed,
  warmups) runs in `main.py`'s `_post_boot()` background thread — never block the
  startup/lifespan path.
- **Email path is Resend → Gmail** (SendGrid removed — don't reintroduce).
  **Telephony is SignalWire** via the twilio-compat module (not Twilio).

## Where things live (backend/app)

- `outreach.py` — the email send ladder. `deliver()` (Outbox) and
  `dispatch_email()` (Send buttons / EverQuote / autopilot) both go Resend → Gmail.
- `integrations/` — `gmail.py` (per-business mailbox routing), `resend.py`,
  `voice.py` + `twilio_voice.py` (SignalWire), `sms.py`, `telco.py`.
- `conversation_engine.py` + `routers/conversations.py` — structured call logging,
  dashboard, renewal pipeline, weekly learnings.
- `models.py` — all tables. `config.py` — settings (many per-business defaults).
- `runtime_config.py` — which settings are editable in the Setup UI + status.
- `mailbox_pool.py`, `deliverability.py` — sending-capacity views.
- `everquote.py` — the (currently only first-class) lead source.

## Known direction (see `.github/autonomous-improver.md` for the full backlog)

The app hard-codes one fixed business set + brand names/emails in ~15 places.
We're moving to a **config-driven Business/Brand registry** so adding a business
is a form entry, not a code change — same plug-and-play goal for API connections.
Prefer registry-driven over hard-coded whenever you touch this area.

## House rules

- Draft PRs; the owner merges. One concern per PR. Tests green before opening.
- Never commit secrets. Never put a model identifier in commits/PRs/code.
- Match surrounding style; write code that reads like what's already there.
