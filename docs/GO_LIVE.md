# Go-Live — the one page

Everything to take Bruno AI Workforce live, in order. Run it once; after that the
system is self-driving. All commands run in **Google Cloud Shell** (project
already set to `bruno-ai-workforce`).

---

## 0. Prerequisites (one-time, skip if done)
```bash
gcloud config set project bruno-ai-workforce
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  containerregistry.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com
```
A **Cloud SQL for PostgreSQL** instance is the datastore; the backend's
`DATABASE_URL` already points at it. New tables auto-create on boot — no migrations.

---

## 1. Deploy
```bash
cd ~/Bruno-AI-Workforce
git checkout main && git pull origin main
./deploy.sh
```
Builds + deploys both Cloud Run services (~5–8 min). Ends with `✅ Deploy complete.`

---

## 2. Secrets — enter once, vaulted forever
```bash
cp .env.production.example .env.production   # then edit and fill in your keys
./scripts/setup-secrets.sh                    # stores them in Secret Manager + wires the service
```
- `.env.production` is **gitignored** — secrets never hit chat or git.
- Cloud Run reads them on every future deploy automatically. **You never retype them.**
- **Rotate** a key later: edit `.env.production`, re-run `./scripts/setup-secrets.sh`, then `./deploy.sh`.

**What goes in `.env.production`:**

| Key | Needed for | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | all AI (emails, posts, images) | platform.openai.com |
| `SECRET_KEY` | auth signing | any random 32+ char string |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | your dashboard login | you choose |
| `CRON_SECRET` | protects the scheduler endpoints | any random string |
| `GMAIL_APP_PASSWORD` | sending cold emails (personal) | Google Account → Security → App passwords |
| `INSURANCE_GMAIL_APP_PASSWORD` | Thrust mailbox sending | App password for that mailbox |
| `JOBS_API_KEY` | LinkedIn/Indeed/Glassdoor jobs | RapidAPI → JSearch |
| `GCS_BUCKET` | hosting generated post images | a public GCS bucket (see step 4) |
| `SOCIAL_AUTO_PUBLISH` / `INSTAGRAM_AUTO_PUBLISH` | auto-posting | set `true` when ready |

> `DATABASE_URL` is already on the service — do **not** add it.

---

## 3. Schedule the autopilot
```bash
CRON_SECRET='same-value-as-step-2' ./scripts/setup-scheduler.sh
```
Creates: full cycle **6 AM**, lead + cold-email passes at **noon & 5 PM**, inbound
reply sync every **30 min**, follow-ups **9 AM & 2 PM**.

---

## 4. (Optional) Image bucket for auto-posting
Needed only for auto-generated social images:
```bash
gcloud storage buckets create gs://YOUR-BUCKET --location=us
gcloud storage buckets add-iam-policy-binding gs://YOUR-BUCKET \
  --member=allUsers --role=roles/storage.objectViewer
```
Put `GCS_BUCKET=YOUR-BUCKET` in `.env.production` (step 2).

---

## 5. Connect your accounts
Open the dashboard, sign in (`ADMIN_EMAIL` / `ADMIN_PASSWORD`), go to **Connections**:

| Platform | Paste | Guide |
|---|---|---|
| Instagram | `access_token`, `ig_user_id` | `docs/INSTAGRAM_CONNECT.md` |
| Facebook | `page_access_token`, `page_id` | same Meta app |
| LinkedIn | `access_token`, `author_urn` | LinkedIn app, `w_member_social` |
| X | `access_token` | X dev portal (paid tier) |
| Spotify | `access_token`, `artist_id` | Spotify dev app |

Find the dashboard URL:
```bash
gcloud run services describe bruno-ai-workforce-front --region northamerica-northeast1 --format='value(status.url)'
```
> Social **posting** requires platform app review (Instagram `instagram_content_publish`,
> Facebook `pages_manage_posts`, etc.). Reading stats works immediately.

---

## 6. (Optional) Automatic deploys on every merge
So you never run `./deploy.sh` again — see `docs/DEPLOY.md` § "Automatic deploys":
create a `gha-deployer` service account and add repo secrets `GCP_SA_KEY` +
`GCP_PROJECT_ID`. After that, merging to `main` deploys itself.

---

## 7. Verify
```bash
curl https://ai-workforce-746155486511.europe-west1.run.app/health   # {"status":"ok"}
```
In the dashboard: **Daily Brief** loads → click **Run agents** for one full cycle now.
Check **Money**, **CRM**, **Instagram Planner** (live account), **Outbox**
(sent emails + AI-drafted replies).

---

## The minimum to get value today
Steps **1 → 2 → 3** with just `OPENAI_API_KEY` + `GMAIL_APP_PASSWORD` set.
Everything else (jobs key, socials, money, images) layers on whenever you're ready.

## What runs on its own after this
- **6 AM / noon / 5 PM** — find leads + send cold emails (insurance + restaurants)
- **6 AM** — find 30 jobs ≥75% match, draft applications
- **Daily** — generate + post to every connected social platform
- **Every 30 min** — sync replies, auto-warm-text, AI-draft responses
- **9 AM / 2 PM** — send due follow-ups

You wake up, open the **Daily Brief**, and approve/follow-up. That's the job.
