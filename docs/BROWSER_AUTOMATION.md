# Browser-Use Worker (Application Autopilot)

The browser worker fills forms on **your own / authorized portals** — primarily
job applications. It has two modes and picks automatically:

| Mode | When | What it does |
|------|------|--------------|
| **assist** (default) | automation off, or Playwright not installed | Prepares a ready-to-submit package: field map, AI screening answers, cover letter, deep link. No browser. Works everywhere, zero infra. |
| **automation** | `BROWSER_AUTOMATION_ENABLED=true` **and** Playwright installed | A headless browser navigates the page, fills detectable fields, attaches your resume, screenshots, and **stops for your review**. |

**Human-in-the-loop by default:** it never clicks submit unless
`BROWSER_AUTO_SUBMIT=true`. Leave that off for job applications — review the
filled form, then submit yourself. Only automate sites you own or are authorized
to automate, and respect each site's Terms of Service.

## Endpoints
- `POST /browser/apply/{job_id}` — prepare a task for a job (status `prepared`).
- `POST /browser/tasks/{id}/run` — execute (assist or automation).
- `GET /browser/tasks` / `GET /browser/tasks/{id}` — list / inspect.

UI: **🤖 Application Autopilot** in the sidebar.

## Enabling full automation
Playwright + Chromium are **not** bundled (keeps the default image small and the
deploy fast). To enable:

1. Add to `backend/requirements.txt` (or a separate `requirements-browser.txt`):
   ```
   playwright==1.49.0
   ```
2. In the backend `Dockerfile`, after `pip install`:
   ```dockerfile
   RUN pip install playwright==1.49.0 && playwright install --with-deps chromium
   ```
   (Adds ~400 MB; consider a separate Cloud Run service for the worker.)
3. Set env vars on the service:
   ```
   BROWSER_AUTOMATION_ENABLED=true
   BROWSER_HEADLESS=true
   BROWSER_AUTO_SUBMIT=false        # keep human-in-the-loop
   APPLICANT_NAME=...
   APPLICANT_EMAIL=...
   APPLICANT_PHONE=...
   APPLICANT_LINKEDIN=...
   APPLICANT_RESUME_PATH=/app/resume.pdf   # baked into the image or mounted
   ```

## Notes & limits
- Cloud Run is request-scoped; long form sessions should stay under the request
  timeout. For heavy use, run the worker as its own service / job.
- Many big job boards (LinkedIn/Indeed) require login + present CAPTCHAs and
  restrict automation in their ToS — prefer company career portals and ATS pages
  (Greenhouse, Lever, Ashby) you're applying through directly.
- The optional [`browser-use`](https://github.com/browser-use/browser-use)
  library (LLM-driven navigation) can be dropped in behind `_drive()` for pages
  whose fields aren't matched by the built-in heuristics.
