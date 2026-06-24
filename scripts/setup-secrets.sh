#!/usr/bin/env bash
#
# Store backend secrets in Google Secret Manager and wire Cloud Run to read them
# by reference. You keep values in ONE place (.env.production), run this ONCE,
# and never retype them again. To rotate a key later: edit .env.production and
# re-run this — it adds a new secret version (no value ever lives in chat/git).
#
#   cp .env.production.example .env.production   # fill it in
#   ./scripts/setup-secrets.sh
set -euo pipefail

FILE="${1:-.env.production}"
SERVICE="${SERVICE:-ai-workforce}"
REGION="${REGION:-europe-west1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"

[ -z "${PROJECT}" ] && { echo "❌ No GCP project. gcloud config set project <id>" >&2; exit 1; }
[ -f "${FILE}" ] || { echo "❌ Missing ${FILE}. Copy .env.production.example and fill it in." >&2; exit 1; }

gcloud services enable secretmanager.googleapis.com --project "${PROJECT}" >/dev/null 2>&1 || true

# The service account Cloud Run runs as (default compute SA if unset).
SA="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --project "${PROJECT}" \
      --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
if [ -z "${SA}" ]; then
  NUM="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
  SA="${NUM}-compute@developer.gserviceaccount.com"
fi

MAPPING="" ; KEYS=""
while IFS='=' read -r key val; do
  key="$(printf '%s' "${key}" | xargs)"
  [ -z "${key}" ] && continue
  case "${key}" in \#*) continue;; esac
  val="${val%$'\r'}"
  secret="BRUNO_${key}"
  if gcloud secrets describe "${secret}" --project "${PROJECT}" >/dev/null 2>&1; then
    printf '%s' "${val}" | gcloud secrets versions add "${secret}" --project "${PROJECT}" --data-file=- >/dev/null
  else
    printf '%s' "${val}" | gcloud secrets create "${secret}" --project "${PROJECT}" \
      --replication-policy=automatic --data-file=- >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "${secret}" --project "${PROJECT}" \
    --member="serviceAccount:${SA}" --role=roles/secretmanager.secretAccessor >/dev/null 2>&1 || true
  MAPPING="${MAPPING}${MAPPING:+,}${key}=${secret}:latest"
  KEYS="${KEYS}${KEYS:+,}${key}"
  echo "  • ${key} → ${secret}"
done < "${FILE}"

[ -z "${MAPPING}" ] && { echo "❌ No variables found in ${FILE}." >&2; exit 1; }

# Remove any literal copies of these keys, then bind them from Secret Manager
# (a name can't be both a literal env var and a secret-backed one).
gcloud run services update "${SERVICE}" --region "${REGION}" --project "${PROJECT}" \
  --remove-env-vars "${KEYS}" >/dev/null 2>&1 || true
gcloud run services update "${SERVICE}" --region "${REGION}" --project "${PROJECT}" \
  --update-secrets "${MAPPING}"

echo "✅ Secrets vaulted in Secret Manager and wired to ${SERVICE}."
echo "   Rotate later: edit .env.production, re-run this, then ./deploy.sh."
