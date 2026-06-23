# Deployment

## 1. Environment

Copy `.env.example` to `.env` and set, at minimum:

- `SECRET_KEY` — long random string (JWT signing).
- `ENCRYPTION_KEY` — Fernet key:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — first dashboard login (seeded on boot).
- `OPENAI_API_KEY` — required for real AI content (otherwise stub output).
- `SMTP_*` + `REPORT_TO_EMAIL` — for the daily CEO email.

## 2. Docker (recommended)

```bash
docker compose up --build -d
```

Services: `db` (Postgres), `redis`, `backend` (FastAPI :8000),
`frontend` (Next.js :3000), `n8n` (:5678). The backend auto-creates tables and
seeds the admin user + agents on first boot.

## 3. n8n (optional external scheduler)

The backend already runs agents on cron via APScheduler. If you prefer n8n:

1. Open http://localhost:5678 and import `n8n/workflows/daily_agents.json`.
2. Create an **HTTP Header Auth** credential named `Bruno API` with header
   `Authorization: Bearer <token>` (token from `POST /auth/token`).
3. Activate the workflow. Set `ENABLE_SCHEDULER=false` in `.env` to avoid
   double-running.

## 3a. Gmail OAuth setup

Outbound/inbound email uses two Gmail accounts (personal + insurance). For each:

1. In Google Cloud Console, create an **OAuth 2.0 Client ID** of type *Desktop
   app* and download `client_secret.json`. Enable the **Gmail API** for the project.
2. Mint a token (logging in as the right account in the browser):
   ```bash
   cd backend
   python -m app.scripts.gmail_auth /path/to/client_secret.json
   ```
3. Copy the printed JSON (one line) into the matching env var:
   - personal → `GOOGLE_TOKEN_JSON`
   - insurance (log in as `bruno@thrustinsurance.com`) → `INSURANCE_GOOGLE_TOKEN_JSON`
4. Confirm `GMAIL_ADDRESS` / `INSURANCE_GMAIL_ADDRESS` match the authorized accounts.

Without these tokens the system runs normally but emails are stored as drafts in
the DB and nothing is sent. With `GMAIL_OUTBOUND_MODE=send`, outreach auto-sends
(respecting `GMAIL_DAILY_SEND_CAP` and same-day dedupe). Set the mode to `draft`
or `send_on_approve` to keep a human in the loop.

> **Note:** `bruno@thrustinsurance.com` must be a Google account (Workspace or
> Gmail) to use the Gmail API. If it's hosted elsewhere, set its SMTP/IMAP
> instead, or use a Google Workspace alias.

## 4. Production hosting

- **Frontend → Vercel.** Set `NEXT_PUBLIC_API_URL` to your backend URL. The app
  uses `output: standalone` so it also runs as the Docker image as-is.
- **Backend → any container host** (Fly.io, Render, ECS, a VM). Point
  `DATABASE_URL` at a managed Postgres (e.g. Supabase). Set all secrets as
  environment variables — never commit `.env`.
- **Database → Supabase or managed Postgres.** Run `backend/db/schema.sql` if you
  want to provision manually; otherwise the app creates tables on boot.
- Restrict CORS (`allow_origins`) in `backend/app/main.py` to your frontend domain.
- Put the backend behind HTTPS and rotate `SECRET_KEY` / `ENCRYPTION_KEY` carefully
  (rotating `ENCRYPTION_KEY` invalidates stored encrypted secrets).

## 5. Health & operations

- `GET /health` — liveness probe (used by the Docker healthcheck).
- `GET /agents` — see each agent's last run time.
- `POST /agents/run-all` — manual full cycle.
- Audit trail: query the `action_logs` table.

## 6. Compliance checklist (cold outreach)

- Keep `messages.approved = false` until a human approves (default).
- Ensure every cold email includes a physical address + unsubscribe link
  (CAN-SPAM / GDPR). The prompts request unsubscribe language; review before send.
- Honor opt-outs: set lead status to `Closed Lost` and stop follow-ups.
