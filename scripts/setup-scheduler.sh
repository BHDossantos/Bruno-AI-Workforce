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
# NB: `create http` takes --headers, but `update http` takes --update-headers —
# so the header flag is set per-branch, not shared.
upsert_job() {
  local name="$1" schedule="$2" path="$3" deadline="${4:-320s}"
  local common=(
    --project "${PROJECT}" --location "${LOCATION}"
    --schedule "${schedule}" --time-zone "${TZ}"
    --uri "${API_URL}${path}" --http-method POST
    --attempt-deadline "${deadline}"
  )
  if gcloud scheduler jobs describe "${name}" --project "${PROJECT}" --location "${LOCATION}" >/dev/null 2>&1; then
    echo "↻ updating ${name} (${schedule})"
    gcloud scheduler jobs update http "${name}" "${common[@]}" \
      --update-headers "X-Cron-Token=${CRON_SECRET}" >/dev/null
  else
    echo "✚ creating ${name} (${schedule})"
    gcloud scheduler jobs create http "${name}" "${common[@]}" \
      --headers "X-Cron-Token=${CRON_SECRET}" >/dev/null
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
# Warm insurance outreach to imported personal contacts — one daily batch that
# drips through your contact list within the mailbox warmup cap.
upsert_job "bruno-contacts-insurance" "15 10 * * *" "/cron/contacts-insurance" "600s"
# Referral asks to engaged insurance leads (warmest source) — weekly, Mondays.
upsert_job "bruno-referrals" "0 11 * * 1" "/cron/referrals" "320s"
# Auto-refresh OAuth tokens daily so social connections never expire.
upsert_job "bruno-refresh-tokens" "0 4 * * *"  "/cron/refresh-tokens" "320s"
# Pull bank balances + transactions from Plaid daily (no-op if no bank linked).
upsert_job "bruno-sync-bank"      "30 5 * * *" "/cron/sync-bank"      "320s"
# Per-platform content loops: top each platform up to its daily cadence with
# channel-optimized content. Runs early so pieces are ready before publishing.
upsert_job "bruno-platform-loops" "0 7 * * *" "/cron/platform-loops" "900s"
# Publish scheduled Content-Factory pieces that are due, a few times a day.
upsert_job "bruno-publish-content" "0 9,13,18 * * *" "/cron/publish-content" "600s"
# Publish approved blog pieces to Medium daily (no-op if Medium isn't connected).
upsert_job "bruno-publish-blog" "30 9 * * *" "/cron/publish-blog" "320s"
# Refresh content engagement metrics nightly (feeds the learning loop).
upsert_job "bruno-content-metrics" "0 23 * * *" "/cron/sync-content-metrics" "320s"
# Poll AI video-generation jobs every 15 min and attach finished clips.
upsert_job "bruno-sync-video" "*/15 * * * *" "/cron/sync-video" "320s"

echo "✅ Scheduler jobs provisioned in ${LOCATION} (project ${PROJECT}, tz ${TZ})."
echo "   List: gcloud scheduler jobs list --location ${LOCATION}"
