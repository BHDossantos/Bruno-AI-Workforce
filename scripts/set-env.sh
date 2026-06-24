#!/usr/bin/env bash
#
# Apply backend env vars from a local .env.production file to the Cloud Run
# service in ONE command.
#
#   cp .env.production.example .env.production   # then edit it
#   ./scripts/set-env.sh
#
# You run this ONCE (and again only when you change a value). Cloud Run keeps
# env vars across normal ./deploy.sh runs — they are NOT reset on each build.
set -euo pipefail

FILE="${1:-.env.production}"
SERVICE="${SERVICE:-ai-workforce}"
REGION="${REGION:-europe-west1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"

[ -z "${PROJECT}" ] && { echo "❌ No GCP project. gcloud config set project <id>" >&2; exit 1; }
[ -f "${FILE}" ] || { echo "❌ Missing ${FILE}. Copy .env.production.example and fill it in." >&2; exit 1; }

# Join non-comment, non-blank KEY=VALUE lines with '@' and use gcloud's custom
# delimiter so values may safely contain commas.
VARS="$(grep -vE '^\s*(#|$)' "${FILE}" | sed 's/[[:space:]]*$//' | paste -sd@ -)"
[ -z "${VARS}" ] && { echo "❌ No variables found in ${FILE}." >&2; exit 1; }

echo "▶ Applying $(grep -cvE '^\s*(#|$)' "${FILE}") env vars to ${SERVICE} (${REGION})…"
gcloud run services update "${SERVICE}" --region "${REGION}" --project "${PROJECT}" \
  --update-env-vars "^@^${VARS}"
echo "✅ Done. These persist across future ./deploy.sh runs."
