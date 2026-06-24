#!/usr/bin/env bash
#
# Provision the Cloud Scheduler jobs that drive the AI workforce. Idempotent:
# creates each job, or updates it if it already exists. Safe to re-run anytime.
#
#   CRON_SECRET='<your cron secret>' ./scripts/setup-scheduler.sh
#
# Optional overrides:
#   PROJECT=<id>          (default: current gcloud project)
#   LOCATION=europe-west1 (App Engine / Scheduler region; default matches backend)
#   API_URL=https://...   (default: the live backend URL)
#   TZ=America/New_York   (default)
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
LOCATION="${LOCATION:-europe-west1}"
API_URL="${API_URL:-https://ai-workforce-746155486511.europe-west1.run.app}"
TZ="${TZ:-America/New_York}"

if [ -z "${PROJECT}" ]; then echo "❌ No GCP project. gcloud config set project <id>" >&2; exit 1; fi
if [ -z "${CRON_SECRET:-}" ]; then echo "❌ Set CRON_SECRET (must match the backend's CRON_SECRET env var)." >&2; exit 1; fi

gcloud services enable cloudscheduler.googleapis.com --project "${PROJECT}" >/dev/null 2>&1 || true

# upsert_job <name> <schedule> <path> [attempt_deadline]
upsert_job() {
  local name="$1" schedule="$2" path="$3" deadline="${4:-320s}"
  local common=(
    --project "${PROJECT}" --location "${LOCATION}"
    --schedule "${schedule}" --time-zone "${TZ}"
    --uri "${API_URL}${path}" --http-method POST
    --headers "X-Cron-Token=${CRON_SECRET}"
    --attempt-deadline "${deadline}"
  )
  if gcloud scheduler jobs describe "${name}" --project "${PROJECT}" --location "${LOCATION}" >/dev/null 2>&1; then
    echo "↻ updating ${name} (${schedule})"
    gcloud scheduler jobs update http "${name}" "${common[@]}" >/dev/null
  else
    echo "✚ creating ${name} (${schedule})"
    gcloud scheduler jobs create http "${name}" "${common[@]}" >/dev/null
  fi
}

# Full CEO → Commander → Agent cycle every morning (jobs + leads + cold emails
# + the executive report). Long deadline since it runs every agent.
upsert_job "bruno-daily-run"  "0 6 * * *"   "/cron/run-all"  "1800s"
# Lead-gen + auto cold-email pass 3× a day (noon & 5 PM in addition to the 6 AM
# full run) — each pass finds fresh prospects AND sends their cold emails.
upsert_job "bruno-leads-noon" "0 12 * * *"  "/cron/leads"    "1200s"
upsert_job "bruno-leads-eve"  "0 17 * * *"  "/cron/leads"    "1200s"
# Sync inbound replies (classify + auto warm-text) frequently.
upsert_job "bruno-inbound"    "*/30 * * * *" "/cron/inbound"  "320s"
# Process due follow-ups twice a day on business days.
upsert_job "bruno-followups"  "0 9,14 * * 1-5" "/cron/followups" "320s"

echo "✅ Scheduler jobs provisioned in ${LOCATION} (project ${PROJECT}, tz ${TZ})."
echo "   List: gcloud scheduler jobs list --location ${LOCATION}"
