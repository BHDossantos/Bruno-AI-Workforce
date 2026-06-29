"""Browser-Use worker — drives a headless browser to fill forms on your own /
authorized portals (primarily job applications).

Two modes, chosen automatically:
- **automation** — when ``browser_automation_enabled`` is set AND Playwright is
  installed: a real headless browser navigates the page, fills detectable fields,
  attaches your resume, screenshots, and STOPS for review (it only clicks submit
  when ``browser_auto_submit`` is on — human-in-the-loop by default).
- **assist** — otherwise (default, and in CI/deploy): no browser is launched; the
  worker prepares a ready-to-submit package (field map + AI screening answers +
  cover letter) and a deep link, so it's useful everywhere with zero infra.

Use only on portals you own or are authorized to automate, and respect each
site's terms of service.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .ai import client
from .config import settings
from .models import Application, BrowserTask, Job

log = logging.getLogger("bruno.browser")


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def is_automation_ready() -> bool:
    return bool(settings.browser_automation_enabled) and _playwright_available()


# ── Preparation ───────────────────────────────────────────────────────────────
def _screening_answers(job: Job) -> dict:
    """AI-generate answers to common application screening questions (offline -> {})."""
    prompt = (
        f"Candidate: {settings.applicant_name}, senior engineering leader.\n"
        f"Role: {job.title} at {job.company} ({job.location}).\n"
        "Answer these application screening questions concisely as the candidate. "
        'Return JSON mapping each question to a short answer for: '
        '"why_interested", "authorized_to_work", "require_sponsorship", '
        '"open_to_relocation", "salary_expectation", "notice_period".'
    )
    ans = client.complete_json(prompt, system="You output only valid JSON.")
    return ans if isinstance(ans, dict) else {}


def _field_map_for(job: Job) -> dict:
    """Build the ready-to-submit fill package from Bruno's authoritative profile."""
    from . import applicant_profile
    name = settings.applicant_name.strip()
    first, _, last = name.partition(" ")
    # Screening answers come straight from the profile (no AI guessing on
    # work-auth/salary/etc.); per-job AI fills any extras.
    return {
        **applicant_profile.flat_fields(),
        "full_name": name, "first_name": first, "last_name": last,
        "resume_path": settings.applicant_resume_path,
        "cover_letter": job.cover_letter or "",
        "answers": {**applicant_profile.SCREENING, **_screening_answers(job)},
        "short_answers": applicant_profile.SHORT_ANSWERS,
    }


def prepare_job_application(db: Session, job_id: str) -> BrowserTask | None:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None
    field_map = _field_map_for(job)
    # Ensure an Application row exists and reflects autopilot prep.
    app = db.query(Application).filter(Application.job_id == job.id).first()
    if not app:
        app = Application(job_id=job.id)
        db.add(app)
    app.status = "Preparing"
    task = BrowserTask(kind="job_application", target_url=job.url, entity_type="job",
                       entity_id=job.id, status="prepared", field_map=field_map)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def autoprepare_for_job(db: Session, job: Job) -> BrowserTask | None:
    """Pre-build the fill package for a freshly-sourced job so it lands in the
    Apply Queue genuinely one-click — WITHOUT touching the Application status
    (the job hunter owns that). Skips jobs that already have a task. Best-effort."""
    if not job or not job.url:
        return None
    existing = (db.query(BrowserTask)
                .filter(BrowserTask.entity_type == "job", BrowserTask.entity_id == job.id)
                .first())
    if existing:
        return existing
    task = BrowserTask(kind="job_application", target_url=job.url, entity_type="job",
                       entity_id=job.id, status="prepared", field_map=_field_map_for(job))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# ── Execution ─────────────────────────────────────────────────────────────────
# Map a form field's identifiers to our field_map keys by keyword.
_KEYWORDS = [
    ("email", "email"), ("e-mail", "email"),
    ("phone", "phone"), ("mobile", "phone"), ("tel", "phone"),
    ("linkedin", "linkedin"),
    ("first", "first_name"), ("last", "last_name"), ("surname", "last_name"),
    ("full name", "full_name"), ("fullname", "full_name"), ("your name", "full_name"),
    ("name", "full_name"),
    ("github", "github"), ("portfolio", "github"),
    ("street", "address"), ("address", "address"),
    ("city", "city"), ("state", "state"), ("province", "state"),
    ("zip", "zip"), ("postal", "zip"), ("country", "country"),
    ("current title", "current_title"), ("current company", "current_employer"),
    ("employer", "current_employer"), ("company", "current_employer"),
    ("desired salary", "target_salary"), ("expected salary", "target_salary"),
    ("salary", "target_salary"), ("compensation", "target_salary"),
    ("start date", "available_start_date"), ("available", "available_start_date"),
    ("years of experience", "years_experience"), ("experience", "years_experience"),
    ("sponsor", "require_sponsorship"), ("visa", "require_sponsorship"),
    ("authorized", "authorized_us"), ("work authorization", "authorized_us"),
    ("citizen", "us_citizen"), ("relocat", "open_to_relocation"),
    ("cover", "cover_letter"), ("message", "cover_letter"), ("why", "cover_letter"),
]


def _match_field(identifier: str, field_map: dict) -> str | None:
    ident = (identifier or "").lower()
    for kw, key in _KEYWORDS:
        if kw in ident and field_map.get(key):
            return str(field_map[key])
    return None


def _drive(task: BrowserTask, auto_submit: bool, cookies: list | None = None) -> dict:  # pragma: no cover - needs a browser
    """Real browser run via Playwright. Returns a result dict.

    cookies (optional) authenticate the session for portals that gate the form
    behind a login (LinkedIn/Indeed Easy Apply) — supply your own session cookies.
    """
    from playwright.sync_api import sync_playwright

    fm = task.field_map or {}
    filled, shot = [], f"/tmp/browser_task_{task.id}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.browser_headless)
        context = browser.new_context()
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception:
                log.warning("could not load session cookies for task %s", task.id)
        page = context.new_page()
        page.goto(task.target_url, wait_until="domcontentloaded", timeout=45000)

        for el in page.query_selector_all("input, textarea"):
            try:
                ident = " ".join(filter(None, [
                    el.get_attribute("name"), el.get_attribute("id"),
                    el.get_attribute("placeholder"), el.get_attribute("aria-label")]))
                itype = (el.get_attribute("type") or "").lower()
                if itype == "file" and fm.get("resume_path"):
                    el.set_input_files(fm["resume_path"]); filled.append("resume")
                    continue
                if itype in ("hidden", "submit", "button", "checkbox", "radio"):
                    continue
                val = _match_field(ident, fm)
                if val:
                    el.fill(val); filled.append(ident.strip()[:40])
            except Exception:
                continue

        page.screenshot(path=shot, full_page=True)
        submitted = False
        if auto_submit:
            btn = page.query_selector("button[type=submit], input[type=submit]")
            if btn:
                btn.click(); page.wait_for_timeout(2000); submitted = True
        browser.close()
    return {"filled": filled, "screenshot": shot, "submitted": submitted,
            "fields_filled": len(filled)}


def run(db: Session, task_id: str, auto_submit: bool | None = None,
        cookies: list | None = None) -> BrowserTask | None:
    task = db.query(BrowserTask).filter(BrowserTask.id == task_id).first()
    if not task:
        return None
    if auto_submit is None:
        auto_submit = settings.browser_auto_submit
    task.updated_at = datetime.now(timezone.utc)

    if is_automation_ready() and task.target_url:
        task.mode, task.status = "automation", "running"
        db.commit()
        try:
            res = _drive(task, auto_submit, cookies=cookies)
            task.status = "submitted" if res.get("submitted") else "needs_review"
            task.result = res
        except Exception as exc:
            log.exception("Browser task %s failed", task_id)
            task.status, task.result = "failed", {"error": str(exc)}
    else:
        # Assist mode — everything is prepared; a human submits on the page.
        task.mode, task.status = "assist", "needs_review"
        task.result = {"assist": True, "fields_ready": list((task.field_map or {}).keys()),
                       "instructions": "Open the application URL and paste the prepared "
                                       "answers/cover letter; attach your resume.",
                       "reason": "automation disabled or Playwright not installed"}
    db.commit()
    db.refresh(task)
    return task


def _out(t: BrowserTask) -> dict:
    return {"id": str(t.id), "kind": t.kind, "target_url": t.target_url,
            "entity_type": t.entity_type, "entity_id": str(t.entity_id) if t.entity_id else None,
            "status": t.status, "mode": t.mode, "field_map": t.field_map, "result": t.result,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "automation_ready": is_automation_ready()}


def list_tasks(db: Session, limit: int = 50) -> list[dict]:
    rows = db.query(BrowserTask).order_by(BrowserTask.created_at.desc()).limit(limit).all()
    return [_out(t) for t in rows]


def get_task(db: Session, task_id: str) -> dict | None:
    t = db.query(BrowserTask).filter(BrowserTask.id == task_id).first()
    return _out(t) if t else None
