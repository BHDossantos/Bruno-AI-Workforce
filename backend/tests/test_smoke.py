"""End-to-end smoke tests for the Bruno AI Workforce backend."""
from app.agents import AGENTS
from app.agents.insurance import InsuranceAgent
from app.agents.job_hunter import JobHunterAgent
from app.agents.music import MusicAgent

from app.ai import skills
from app.integrations import apollo, jobs_api, providers

from .conftest import requires_db


# ── Pure logic (no DB) ───────────────────────────────────────────────────────
def test_job_scoring_rules():
    score, breakdown = JobHunterAgent.score_job(
        {"title": "Director SRE", "description": "cloud AI data platform",
         "remote": True, "salary_min": 220_000}
    )
    assert score == 100
    assert breakdown == {
        "remote": 25, "salary_200k_plus": 25, "leadership": 20,
        "cloud_sre_match": 20, "ai_data_platform": 10,
    }


def test_low_scoring_job_is_filtered():
    score, _ = JobHunterAgent.score_job(
        {"title": "Software Engineer", "description": "react frontend",
         "remote": False, "salary_min": 120_000}
    )
    assert score < 70


def test_insurance_and_music_scoring():
    assert InsuranceAgent.score_lead(
        {"email": "a@b.c", "phone": "1", "website": "x", "segment": "commercial"}
    ) == 100
    assert MusicAgent.genre_match("Samba") == 100
    assert MusicAgent.genre_match("Techno") == 50


def test_all_agents_registered():
    assert set(AGENTS) == {
        "job_hunter", "insurance", "savorymind", "music", "instagram", "ceo_dashboard"
    }


# ── Live-source integrations (no network; key-gated) ─────────────────────────
def test_live_sources_disabled_without_keys():
    assert apollo.is_configured() is False
    assert jobs_api.is_configured() is False
    assert apollo.fetch_commercial_leads(10) == []
    assert jobs_api.fetch_jobs(["Director SRE"], limit=5) == []


def test_jobs_api_maps_jsearch_payload():
    mapped = jobs_api._map({
        "job_title": "Director SRE", "employer_name": "Acme",
        "job_city": "Boston", "job_state": "MA", "job_is_remote": False,
        "job_min_salary": 210000, "job_max_salary": 260000,
        "job_publisher": "Indeed", "job_apply_link": "https://x/y",
        "job_description": "Lead reliability.",
    })
    assert mapped["title"] == "Director SRE"
    assert mapped["company"] == "Acme"
    assert mapped["location"] == "Boston, MA"
    assert mapped["salary_min"] == 210000 and mapped["source"] == "indeed"


def test_marketing_skills_are_packaged_and_loaded():
    assert "cold" in skills.load_skill("cold-email").lower()
    assert skills.load_skill("copywriting")
    sp = skills.system_prompt("cold-email", "copywriting")
    assert "Skill: cold-email" in sp and "Skill: copywriting" in sp
    assert "valid JSON" in sp  # the agents still get JSON output instruction


def test_email_template_wraps_body_with_signature_and_footer():
    from app import email_template

    out = email_template.render("Hi there\nThanks", account="insurance")
    assert "Hi there" in out
    assert "Thrust Insurance" in out  # signature/footer
    assert "unsubscribe" in out.lower()  # CAN-SPAM footer
    assert email_template.render(None) is None


def test_providers_fallback_meets_targets_without_keys():
    assert len(providers.fetch_insurance_leads("commercial", 100)) == 100
    assert len(providers.fetch_restaurants(100)) == 100
    assert len(providers.fetch_jobs(60)) == 60


# ── Full pipeline (needs PostgreSQL) ─────────────────────────────────────────
@requires_db
def test_health_and_auth(client, auth_headers):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/jobs").status_code == 401  # RBAC: no token
    assert client.get("/auth/me", headers=auth_headers).status_code == 200


@requires_db
def test_full_daily_cycle_hits_targets(client, auth_headers):
    """Run every agent and assert the daily success-criteria targets are met."""
    resp = client.post("/agents/run-all", headers=auth_headers)
    assert resp.status_code == 200

    summary = client.get("/dashboard/summary", headers=auth_headers).json()
    assert summary["jobs_found"] == 25
    assert summary["insurance_leads"] == 200
    assert summary["restaurant_prospects"] == 100
    assert summary["music_playlists"] == 50
    assert summary["instagram_targets"] == 100

    assert len(client.get("/jobs", headers=auth_headers).json()) == 25
    assert len(client.get("/instagram/targets", headers=auth_headers).json()) == 100
    assert len(client.get("/music/influencers", headers=auth_headers).json()) == 25

    report = client.get("/reports/latest", headers=auth_headers).json()
    assert report is not None and report["metrics"]["insurance_leads"] == 200


@requires_db
def test_outbound_messages_created_per_account(client, auth_headers):
    """Agents create outbound Message rows; insurance routes via its own mailbox."""
    msgs = client.get("/messages?limit=500", headers=auth_headers).json()
    assert len(msgs) >= 300  # 200 insurance + 100 savorymind cold emails

    insurance = [m for m in msgs if m["from_account"] == "insurance"]
    personal = [m for m in msgs if m["from_account"] == "personal"]
    assert len(insurance) == 200
    assert len(personal) >= 100
    # Gmail is not configured in CI, so nothing is actually sent.
    assert all(m["status"] == "Drafted" for m in msgs)


@requires_db
def test_inbound_sync_is_safe_without_gmail(client, auth_headers):
    resp = client.post("/inbound/sync", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"scanned": 0, "matched": 0}


@requires_db
def test_sms_inbound_webhook_and_threads(client, auth_headers):
    # Inbound webhook is public (no auth) and stores the text.
    r = client.post("/sms/inbound", data={"From": "+15551234567", "Body": "yes interested"})
    assert r.status_code == 200
    threads = client.get("/sms/threads", headers=auth_headers).json()
    assert any(t["phone"] == "+15551234567" for t in threads)
    thread = client.get("/sms/thread?phone=%2B15551234567", headers=auth_headers).json()
    assert thread["messages"] and thread["messages"][0]["direction"] == "inbound"


@requires_db
def test_social_queue_endpoint(client, auth_headers):
    r = client.get("/outreach/social", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@requires_db
def test_followup_engine_processes_due_steps(client, auth_headers):
    """A due follow-up generates a new outreach Message and is marked completed."""
    from datetime import date, timedelta

    from app import followups, models
    from app.database import SessionLocal

    db = SessionLocal()
    lead = models.Lead(segment="commercial", email="fu-test@example.com",
                       company_name="FU Co", status="Drafted")
    db.add(lead)
    db.flush()
    db.add(models.Message(channel="email", entity_type="lead", entity_id=lead.id,
                          to_email="fu-test@example.com", from_account="insurance",
                          subject="hi", body="first touch", status="Sent"))
    db.add(models.FollowUp(entity_type="lead", entity_id=lead.id, step=1,
                           due_date=date.today() - timedelta(days=1), completed=False))
    db.commit()

    res = followups.process_due_followups(db)
    assert res["due"] >= 1
    # a follow-up Message was created (in addition to the first touch)
    n = db.query(models.Message).filter(models.Message.entity_id == lead.id).count()
    assert n >= 2
    db.close()
