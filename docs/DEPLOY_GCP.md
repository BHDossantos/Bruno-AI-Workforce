# Deploy on Google Cloud (Cloud Run + Cloud Scheduler)

Cost-effective, always-available GCP setup: the backend runs on **Cloud Run**
(scales to zero), **Cloud Scheduler** fires the daily agents/follow-ups/inbound
via the secure `/cron/*` endpoints, and Postgres is a free managed DB. Frontend
goes on Vercel. Typical cost: a few cents/month (free tiers cover most of it).

## 0. Prereqs
- Install the gcloud CLI and log in: `gcloud auth login`
- Use your existing project: `gcloud config set project <YOUR_PROJECT_ID>`
- Enable services:
  ```bash
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
      cloudscheduler.googleapis.com
  ```

## 1. Database (free, persistent)
Cloud SQL works but costs ~$8/mo. To stay ~free, use **Supabase** or **Neon**
(both have a free persistent Postgres):
1. Create a project at supabase.com (or neon.tech).
2. Copy the connection string (looks like `postgresql://user:pass@host:5432/db`).
   Our app auto-converts it to the psycopg driver.

## 2. Deploy the backend to Cloud Run
From the repo root (Cloud Run builds the image from `backend/Dockerfile`):
```bash
gcloud run deploy bruno-backend \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --set-env-vars "ENABLE_SCHEDULER=false,TIMEZONE=America/New_York,OPENAI_MODEL=gpt-4o,GMAIL_OUTBOUND_MODE=draft,GMAIL_ADDRESS=brunodossantos707@gmail.com,INSURANCE_GMAIL_ADDRESS=bruno@thrustinsurance.com,REPORT_TO_EMAIL=brunodossantos707@gmail.com,JOBS_API_HOST=jsearch.p.rapidapi.com,INSURANCE_BUSINESS_NAME=Thrust Insurance,SENDER_NAME=Bruno Dos Santos"
```
Then set the **secrets** (kept out of the command above):
```bash
gcloud run services update bruno-backend --region us-central1 --update-env-vars \
"DATABASE_URL=<supabase-url>,SECRET_KEY=<random>,ENCRYPTION_KEY=<fernet>,CRON_SECRET=<random>,ADMIN_EMAIL=brunodossantos707@gmail.com,ADMIN_PASSWORD=<pw>,OPENAI_API_KEY=<key>,APOLLO_API_KEY=<key>,JOBS_API_KEY=<key>,HUBSPOT_API_KEY=<key>,GOOGLE_TOKEN_JSON=<json>,INSURANCE_GOOGLE_TOKEN_JSON=<json>"
```
> Tip: for the big token JSON values, prefer Secret Manager or the Cloud Run
> console (Variables & Secrets tab) to avoid shell-escaping issues.

Grab the service URL (e.g. `https://bruno-backend-xxxx.a.run.app`) and check
`/health`.

## 3. Cloud Scheduler (the daily automation)
Create jobs that POST to the `/cron/*` endpoints with the token header. Three
jobs keep you in the free tier:
```bash
URL=https://bruno-backend-xxxx.a.run.app
TOKEN=<same CRON_SECRET as above>

gcloud scheduler jobs create http bruno-run-all \
  --schedule "0 6 * * *" --time-zone "America/New_York" \
  --uri "$URL/cron/run-all" --http-method POST \
  --headers "X-Cron-Token=$TOKEN"

gcloud scheduler jobs create http bruno-followups \
  --schedule "0 11 * * *" --time-zone "America/New_York" \
  --uri "$URL/cron/followups" --http-method POST \
  --headers "X-Cron-Token=$TOKEN"

gcloud scheduler jobs create http bruno-inbound \
  --schedule "0 */2 * * *" --time-zone "America/New_York" \
  --uri "$URL/cron/inbound" --http-method POST \
  --headers "X-Cron-Token=$TOKEN"
```
(Prefer per-agent timing? Make one job per agent hitting `/cron/agent/<key>`.)

## 4. Frontend on Vercel
- Import the repo at vercel.com, set **Root Directory = `frontend`**.
- Env: `NEXT_PUBLIC_API_URL = https://bruno-backend-xxxx.a.run.app`.
- Deploy.

## 5. Webhooks
- **Twilio inbound SMS** → `https://bruno-backend-xxxx.a.run.app/sms/inbound`.
- Gmail replies are polled by the `/cron/inbound` job (no webhook needed).

## 6. Go live
1. Verify a manual run: `curl -X POST $URL/cron/run-all -H "X-Cron-Token: $TOKEN"`.
2. Review drafts in the dashboard + Gmail, then set `GMAIL_OUTBOUND_MODE=send`
   (`gcloud run services update ... --update-env-vars GMAIL_OUTBOUND_MODE=send`).
