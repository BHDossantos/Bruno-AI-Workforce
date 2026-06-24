# Frontend shows `{"detail":"Not Found"}` — what's wrong and how to fix it

## Short answer on networking

**No network configuration is needed.** Nothing was missed there:

- The backend Cloud Run service is **public** (Allow unauthenticated).
- Backend CORS is `allow_origins=["*"]`, so the browser can call it from anywhere.
- The frontend talks to the backend over plain **public HTTPS**, using the URL
  baked in at build time (`NEXT_PUBLIC_API_URL`). No VPC, no Serverless VPC
  Connector, no private networking.

So the blank/"Not Found" page is **not** a networking problem.

## The real cause

`https://bruno-ai-workforce-front-...run.app` returns `{"detail":"Not Found"}`.
That JSON is the **FastAPI backend's** 404 response. The Next.js dashboard never
returns that — if the frontend were serving, an unknown path returns an HTML 404,
not JSON.

**Conclusion:** the `bruno-ai-workforce-front` service's *serving revision* is
still running the **backend image**, even though the frontend image now builds
correctly. The build succeeded, but that image was never promoted to serve
traffic on this service. Build success ≠ deploy.

## The fix (pick one)

### Option A — one command, most reliable
From the repo root, with gcloud installed and the project selected:

```bash
gcloud run deploy bruno-ai-workforce-front \
  --source frontend \
  --region northamerica-northeast1 \
  --allow-unauthenticated \
  --port 8080
```

`--source frontend` uses `frontend/Dockerfile` directly, builds the Next.js
image, and routes 100% of traffic to it in one step. When it finishes, open the
service URL — it now serves the dashboard.

### Option B — build + deploy via the committed config
This repo now has `cloudbuild.frontend.yaml`, which builds **and** deploys so the
gap can't happen again:

```bash
gcloud builds submit --config cloudbuild.frontend.yaml .
```

To make every push auto-deploy: Cloud Build → Triggers → edit the frontend
trigger → Configuration = *Cloud Build configuration file*, file =
`cloudbuild.frontend.yaml`.

### Option C — verify/repair in the Console (no CLI)
1. Cloud Run → **bruno-ai-workforce-front** → **Revisions** tab.
2. Look at the revision serving 100% traffic → its **Container image**.
   - If it's a `.../ai-workforce:...` (backend) image → that's the bug.
3. Click **Edit & Deploy New Revision** → set Container image to the frontend
   image (`gcr.io/bruno-ai-workforce/bruno-ai-workforce-front:...`), Port `8080`
   → Deploy. Or use the **Logs** tab: frontend logs say `▲ Next.js ... Listening
   on 8080`; backend logs say `Uvicorn running`. That tells you which image is live.

## Sanity checks after deploying
- `curl https://bruno-ai-workforce-front-...run.app` → returns HTML (`<!DOCTYPE html>`),
  not JSON.
- Open `/login` in the browser → the login page renders.
- Log in → the dashboard loads data from the backend (confirms the baked
  `NEXT_PUBLIC_API_URL` and CORS both work).
