# Relaunch on Render (the cheap, off-Google home)

Google billing is gone, so this is a **fresh start** — new database, no data carried
over. EverQuote re-sources your leads once the app is up; historical call/text logs
don't survive the move. Total cost starts around **$7/mo** (backend Starter + free
frontend + free DB), vs the $500–2,800/mo on Google.

The repo already carries the blueprint (`render.yaml`) that stands up the whole app.

## One-time deploy (about 10 minutes)

1. **Create a Render account** at https://render.com and connect your GitHub.
2. **New → Blueprint** → pick the `bhdossantos/bruno-ai-workforce` repo → **Apply**.
   Render reads `render.yaml` and creates three things: the **Postgres DB**, the
   **backend** (`bruno-backend`), and the **frontend** (`bruno-frontend`).
3. **Fill the backend secrets.** Open `bruno-backend` → **Environment** and set the
   `sync: false` values:
   - `ENCRYPTION_KEY` — generate a **new** Fernet key (fresh DB). Any 32-byte
     url-safe base64 string; e.g. run locally:
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - `ADMIN_PASSWORD` — your login password.
   - `OPENAI_API_KEY` — the AI brain (drafts degrade to stubs without it).
   - `RESEND_API_KEY` / `SENDGRID_API_KEY` / `GMAIL_APP_PASSWORD` — email sending
     (optional here; you can also connect them later in the in-app **Setup** page).
   Save → the backend redeploys.
4. **Point the frontend at the backend.** Copy the backend's URL (top of the
   `bruno-backend` page, e.g. `https://bruno-backend-xxxx.onrender.com`). Open
   `bruno-frontend` → **Environment** → set `NEXT_PUBLIC_API_URL` to that URL →
   Save. The frontend rebuilds (Next bakes this in at build time — that's why it's
   a manual step after the backend URL exists).
5. **Log in** at the frontend URL with `ADMIN_EMAIL` / `ADMIN_PASSWORD`, open
   **Setup**, and connect the rest (Twilio/SignalWire, EverQuote, Gmail). Telephony
   still needs your Twilio Toll-Free Verification / SignalWire 10DLC to finish —
   those are carrier-side and unrelated to the host.

Call/SMS webhooks need no configuration: `PUBLIC_BASE_URL` auto-fills from Render's
`RENDER_EXTERNAL_URL`, so the backend hands carriers the right callback URLs itself.

## Two things worth paying for (still cheap)

- **Backend must stay awake.** The scheduler (auto emails/texts/calls, follow-ups)
  only runs while the backend is alive, so keep it on **Starter** ($7/mo), never
  Free — Free sleeps and the automation stops. The frontend may stay Free (a slow
  first load is the only cost).
- **Don't trust the free DB with real data.** Render's **free Postgres is deleted
  after 90 days.** You just lost a database to a billing lapse — switch `bruno-db`
  to a paid plan (`basic-256mb`, ~$7/mo) once there's data you care about.

So a durable setup is ~**$14/mo** (backend + paid DB), still a fraction of Google.

## Keep Places OFF

`PLACES_ENABLED=false` is set in the blueprint on purpose — Google Places Text
Search was ~90% of the old bill. Leave it off; EverQuote is the first-class lead
source. If you ever turn it on, the per-query cooldown + monthly request cap
(`PLACES_QUERY_COOLDOWN_DAYS`, `PLACES_MONTHLY_REQUEST_CAP`) keep it bounded.
