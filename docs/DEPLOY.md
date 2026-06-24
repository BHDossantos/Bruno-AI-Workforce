# Deploy — single command

This is the one-stop runbook. Everything (backend API + frontend dashboard) goes
to **Google Cloud Run** with a single script.

```bash
./deploy.sh           # build + deploy BOTH services
./deploy.sh backend   # backend only
./deploy.sh frontend  # frontend only
```

That's it. Each build pushes a fresh image and promotes it to the live revision.
**New database tables are created automatically on boot — there is no migration
step.**

---

## What gets deployed
| Service | Cloud Run name | Region | Build config |
|---|---|---|---|
| Backend (FastAPI) | `ai-workforce` | `europe-west1` | `cloudbuild.backend.yaml` |
| Frontend (Next.js) | `bruno-ai-workforce-front` | `northamerica-northeast1` | `cloudbuild.frontend.yaml` |

The frontend image bakes in `NEXT_PUBLIC_API_URL` pointing at the backend (set in
`cloudbuild.frontend.yaml`).

## One-time prerequisites
```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  containerregistry.googleapis.com sqladmin.googleapis.com
```
A **Cloud SQL for PostgreSQL** instance is the datastore; point the backend at it
via `DATABASE_URL` (below). Attach it to the service with `--add-cloudsql-instances`
or use the connector, per your existing setup.

## Environment variables (backend)
Set/refresh secrets on the backend service. The app boots without most of these
(it degrades gracefully), but these are the ones that matter in production:

```bash
gcloud run services update ai-workforce --region europe-west1 \
  --update-env-vars \
DATABASE_URL='postgresql+psycopg://USER:PASS@/DB?host=/cloudsql/INSTANCE',\
SECRET_KEY='<random-32+ chars>',\
OPENAI_API_KEY='<your key>',\
ADMIN_EMAIL='brunodossantos707@gmail.com',\
ADMIN_PASSWORD='<your admin password>',\
CRON_SECRET='<shared secret for /cron/*>',\
GMAIL_APP_PASSWORD='<gmail app password>'
```

Useful optional vars (all have safe defaults):
- **Outreach/SMS/Gmail** — see `app/config.py` (Twilio, insurance mailbox, etc.).
- **Lead sourcing** — `LEAD_STATES`, `LEAD_CITIES`, `LEAD_BATCH_SIZE`, `JOBS_API_KEY`.
- **Application Autopilot** — your identity is pre-filled from the résumé
  (`APPLICANT_NAME/EMAIL/PHONE`, résumé baked into the image at
  `/app/assets/resume/`). To turn on real browser automation:
  `BROWSER_AUTOMATION_ENABLED=true` (and add Playwright to the image — see
  [BROWSER_AUTOMATION.md](BROWSER_AUTOMATION.md)). Leave `BROWSER_AUTO_SUBMIT=false`.
  Set `APPLICANT_LINKEDIN` to your profile URL.

## Daily automation (run the AI workforce on a schedule)
One idempotent script provisions all the Cloud Scheduler jobs:
```bash
CRON_SECRET='<same value as the backend CRON_SECRET>' ./scripts/setup-scheduler.sh
```
It creates (or updates) three jobs that call the token-protected `/cron/*`
endpoints:

| Job | Schedule (America/New_York) | Endpoint | What it does |
|---|---|---|---|
| `bruno-daily-run` | 6:00 AM daily | `/cron/run-all` | Full CEO→Commander→Agent cycle |
| `bruno-inbound` | every 30 min | `/cron/inbound` | Sync replies, classify, auto warm-text |
| `bruno-followups` | 9 AM & 2 PM, Mon–Fri | `/cron/followups` | Send due follow-ups |

Override `PROJECT`, `LOCATION`, `API_URL`, or `TZ` via env vars if needed.

## Automatic deploys (CI/CD) — never touch the CLI
`.github/workflows/deploy.yml` deploys **automatically after CI passes on
`main`** (and is runnable by hand from the Actions tab). Set it up once:

**1. Create a deploy service account + key**
```bash
PROJECT=<PROJECT_ID>
gcloud iam service-accounts create gha-deployer --project "$PROJECT" \
  --display-name "GitHub Actions deployer"
SA="gha-deployer@${PROJECT}.iam.gserviceaccount.com"
for ROLE in roles/cloudbuild.builds.editor roles/run.admin \
            roles/iam.serviceAccountUser roles/storage.admin; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$ROLE"
done
gcloud iam service-accounts keys create key.json --iam-account "$SA"
```

**2. Add the repo secrets** (GitHub → Settings → Secrets and variables → Actions):
- `GCP_SA_KEY` — the full contents of `key.json`
- `GCP_PROJECT_ID` — your project id

Then **delete `key.json` locally**. From now on, every merge to `main` that
passes CI deploys both services. (Prefer keyless? Swap `credentials_json` for
Workload Identity Federation in the workflow.)

## Verify
```bash
curl -fsS https://ai-workforce-746155486511.europe-west1.run.app/health   # {"status":"ok"}
```
Open the frontend service URL, sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`,
and the **Daily Brief** should load. Run one full cycle from the home page's
"Run agents" button (or the Cloud Scheduler job).

## Rollback
```bash
gcloud run revisions list --service ai-workforce --region europe-west1
gcloud run services update-traffic ai-workforce --region europe-west1 --to-revisions <REVISION>=100
```
