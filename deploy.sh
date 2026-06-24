#!/usr/bin/env bash
#
# Single deploy — builds AND deploys BOTH services to Cloud Run in one shot.
#
#   ./deploy.sh                    # uses your current gcloud project
#   PROJECT=my-gcp-project ./deploy.sh
#   ./deploy.sh backend            # deploy only the backend
#   ./deploy.sh frontend           # deploy only the frontend
#
# Each cloudbuild config builds the image, pushes it, and promotes it to the
# live Cloud Run revision (no separate deploy step that can be skipped).
# New DB tables are created automatically on boot — there is no migration step.
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
if [ -z "${PROJECT}" ]; then
  echo "❌ No GCP project set. Run: gcloud config set project <PROJECT_ID>" >&2
  exit 1
fi

TARGET="${1:-all}"
echo "▶ Deploying '${TARGET}' to project: ${PROJECT}"

deploy_backend() {
  echo "▶ Backend  → service 'ai-workforce' (europe-west1)…"
  gcloud builds submit --project "${PROJECT}" --config cloudbuild.backend.yaml .
}
deploy_frontend() {
  echo "▶ Frontend → service 'bruno-ai-workforce-front' (northamerica-northeast1)…"
  gcloud builds submit --project "${PROJECT}" --config cloudbuild.frontend.yaml .
}

case "${TARGET}" in
  backend)  deploy_backend ;;
  frontend) deploy_frontend ;;
  all)      deploy_backend; deploy_frontend ;;
  *) echo "Usage: ./deploy.sh [all|backend|frontend]" >&2; exit 1 ;;
esac

echo "✅ Deploy complete."
echo "   Backend : https://ai-workforce-746155486511.europe-west1.run.app/health"
echo "   Frontend: open your bruno-ai-workforce-front service URL"
