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


def test_free_jobs_gated_off_in_tests_and_parse_salary():
    from app.integrations import jobs_free

    assert jobs_free.is_enabled() is False          # ENABLE_FREE_JOBS=false in tests
    assert jobs_free.fetch_jobs(10) == []           # disabled → no network
    assert jobs_free._salary("$180k - $220k") == 180000
    assert jobs_free._salary("210000") == 210000
    assert jobs_free._salary(None) is None
    # Skill-fit filter: keep cloud/leadership roles, drop unrelated ones.
    assert jobs_free._fits("Director of Site Reliability", "cloud platform") is True
    assert jobs_free._fits("Barista", "make coffee") is False


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
    assert "Bruno Dossantos" in out
    assert "tel:+16175683000" in out and "tel:+16039308272" in out  # click-to-call
    assert "unsubscribe" in out.lower()  # CAN-SPAM footer
    assert email_template.render(None) is None

    personal = email_template.render("Hi there", account="personal")
    assert "Bruno Dos Santos, MBA, MSIT" in personal
    assert "tel:+16039308272" in personal
    assert "Thrust Insurance" not in personal  # insurance signature must not leak

    # AI placeholders + sign-off are stripped; only the real signature remains.
    raw = ("Hi [Prospect's Name],\n\nRunning a restaurant is hard.\n\n"
           "Best,\n[Your Name]\n\nP.S. If you'd rather not hear from me, let me know.")
    cleaned = email_template.clean_body(raw)
    assert "[Your Name]" not in cleaned and "[Prospect's Name]" not in cleaned
    assert "Best," not in cleaned and "P.S." not in cleaned
    assert "Hi there," in cleaned
    rendered = email_template.render(raw, account="insurance")
    assert "[Your Name]" not in rendered and "Bruno Dossantos" in rendered


def test_reply_classifier_safe_without_ai():
    from app import classify

    out = classify.classify_reply("yes I'm interested, let's talk")
    assert out["intent"] in {"interested", "question", "objection", "not_interested", "unsubscribe", "neutral"}
    assert out["status"]  # always maps to a status
    assert classify.classify_reply("")["status"] == "Replied"


def test_emails_never_sent_to_placeholder_addresses():
    from app import outreach

    assert outreach.is_real_email("jane@acme.com") is True
    for bad in ["x@example.com", "y@test.com", "z@host.invalid", "a@b.local", "noatsign", ""]:
        assert outreach.is_real_email(bad) is False


def test_real_only_mode_emits_no_synthetic_data():
    from app.config import settings
    from app.integrations import providers

    settings.allow_synthetic_fallback = False
    try:
        # No Apollo/JSearch keys in tests → real-only mode yields nothing synthetic.
        assert providers.fetch_insurance_leads("commercial", 100) == []
        assert providers.fetch_restaurants(100) == []
        assert providers.fetch_jobs(60) == []
        assert providers.fetch_playlists(50) == []
    finally:
        settings.allow_synthetic_fallback = True


def test_osm_lead_engine_offline_behavior():
    from app.config import settings
    from app.integrations import osm_leads

    assert osm_leads._clean_email("Info@Acme.com") == "info@acme.com"
    assert osm_leads._clean_email("logo@2x.png") is None
    assert osm_leads._clean_email("x@example.com") is None

    # States take precedence and produce state-level (admin_level 4) areas.
    old_c, old_s = settings.lead_cities, settings.lead_states
    settings.lead_states = "Massachusetts,New Hampshire,Florida"
    settings.lead_cities = "Boston"
    try:
        areas = osm_leads._areas()
        labels = [a[0] for a in areas]
        assert labels == ["Massachusetts", "New Hampshire", "Florida"]  # states win
        assert all('"admin_level"="4"' in a[1] for a in areas)
    finally:
        settings.lead_cities, settings.lead_states = old_c, old_s
    # Disabled (and never hits the network) when no states/cities configured.
    old_c, old_s = settings.lead_cities, settings.lead_states
    settings.lead_cities = ""
    settings.lead_states = ""
    try:
        assert osm_leads.is_enabled() is False
        assert osm_leads.fetch_commercial_leads(10) == []
        assert osm_leads.fetch_restaurants(10) == []
    finally:
        settings.lead_cities = old_c
        settings.lead_states = old_s


def test_places_source_disabled_without_key():
    from app.integrations import email_finder, places

    assert places.is_configured() is False
    assert places.fetch_commercial_leads(10) == []
    assert places.fetch_restaurants(10) == []
    # Shared email finder cleans correctly.
    assert email_finder.clean_email("Sales@Acme.com") == "sales@acme.com"
    assert email_finder.clean_email("hero@2x.png") is None


def test_providers_fallback_meets_targets_without_keys():
    assert len(providers.fetch_insurance_leads("commercial", 100)) == 100
    assert len(providers.fetch_restaurants(100)) == 100
    assert len(providers.fetch_jobs(60)) == 60


# ── Connect-any-account platform (no DB) ─────────────────────────────────────
def test_provider_registry_is_well_formed():
    from app.integrations import registry

    keys = {p["key"] for p in registry.list_providers()}
    # A representative spread of categories the user can connect.
    for must in ["instagram", "facebook", "linkedin", "gmail", "hubspot",
                 "shopify", "stripe", "meta_ads", "google_ads", "twilio_sms"]:
        assert must in keys
    for p in registry.list_providers():
        assert p["name"] and p["category"] and p["capabilities"]
        assert set(p["stages"]).issubset(set(registry.STAGES))
        # every secret field is a known field
        assert registry.secret_field_keys(p["key"]) <= {f["key"] for f in p["fields"]}


def test_funnel_plan_maps_capabilities_to_stages():
    from app import funnel

    plan = funnel.build_plan("gmail")
    stages = {s["stage"] for s in plan["stages"]}
    # Gmail has email_auto + lead_capture → capture/nurture/convert covered.
    assert {"capture", "nurture", "convert"}.issubset(stages)
    assert plan["auto_actions"] >= 1
    # Unknown provider degrades gracefully.
    assert funnel.build_plan("nope").get("unsupported") is True


def test_funnel_respects_tos_assist_vs_auto():
    from app import funnel

    li = funnel.build_plan("linkedin")
    li_actions = {(a["capability"], a["mode"]) for s in li["stages"] for a in s["actions"]}
    # LinkedIn publishing & DMs must stay assist-only (no bot automation) to be
    # ToS-safe. (Read-only analytics may still run automatically.)
    assert ("publish_assist", "assist") in li_actions
    assert ("dm_assist", "assist") in li_actions
    assert not any(cap in ("publish_auto",) for cap, _ in li_actions)

    ig = funnel.build_plan("instagram")
    ig_actions = {(a["capability"], a["mode"]) for s in ig["stages"] for a in s["actions"]}
    assert ("publish_auto", "auto") in ig_actions       # official API posting
    assert ("dm_assist", "assist") in ig_actions        # DMs stay one-click


def test_gmail_app_password_enables_sending_config():
    from app.config import settings
    from app.integrations import gmail

    old = settings.gmail_app_password
    try:
        settings.gmail_app_password = ""
        assert gmail._smtp_configured("personal") is False
        settings.gmail_app_password = "abcd efgh ijkl mnop"  # App Password
        assert gmail._smtp_configured("personal") is True
        assert gmail.is_configured("personal") is True  # send path now enabled

        # Insurance with no Thrust creds: via-personal reply-to mode sends from
        # the personal address but routes replies to the Thrust inbox.
        old_rt = settings.insurance_via_personal_reply_to
        try:
            settings.insurance_via_personal_reply_to = True
            login, pw, frm, reply = gmail._smtp_login("insurance")
            assert login == settings.gmail_address          # logs in as personal
            assert frm == settings.gmail_address            # From = personal
            assert reply == settings.insurance_gmail_address  # Reply-To = Thrust
            assert gmail.is_configured("insurance") is True
        finally:
            settings.insurance_via_personal_reply_to = old_rt
    finally:
        settings.gmail_app_password = old


def test_analytics_funnel_is_monotonic():
    from app.routers.analytics import _funnel

    statuses = ["New", "Sent", "Opened", "Replied", "Interested", "Closed Won", "Closed Lost"]
    f = {d["stage"]: d["count"] for d in _funnel(statuses)}
    assert f["Sourced"] == 7              # everyone is sourced
    assert f["Contacted"] >= f["Opened"] >= f["Replied"] >= f["Interested"] >= f["Won"]
    assert f["Won"] == 1                  # one Closed Won
    assert f["Replied"] == 3             # Replied, Interested, Closed Won


def test_crm_token_falls_back_to_env_without_connection():
    from app.config import settings
    from app.integrations import crm

    old = settings.hubspot_api_key
    try:
        settings.hubspot_api_key = ""
        assert crm.resolve_token(None) is None            # nothing configured -> no push
        assert crm.push_lead({"email": "a@b.com"}, db=None)["ok"] is False
        settings.hubspot_api_key = "env-key"
        assert crm.resolve_token(None) == "env-key"       # env var used as fallback
    finally:
        settings.hubspot_api_key = old


def test_funnel_overview_reports_gaps():
    from app import funnel

    ov = funnel.overview([{"provider": "instagram", "goal": "followers"}])
    assert ov["connected"] == 1
    assert "convert" in ov["gaps"] or ov["stage_coverage"]["attract"] >= 1


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

    from app.config import settings
    batch = settings.lead_batch_size

    summary = client.get("/dashboard/summary", headers=auth_headers).json()
    assert summary["jobs_found"] == 20
    assert summary["insurance_leads"] == batch
    assert summary["restaurant_prospects"] == batch
    assert summary["music_playlists"] == 50
    assert summary["instagram_targets"] == 100

    assert len(client.get("/jobs", headers=auth_headers).json()) == 20
    assert len(client.get("/instagram/targets", headers=auth_headers).json()) == 100
    assert len(client.get("/music/influencers", headers=auth_headers).json()) == 25

    report = client.get("/reports/latest", headers=auth_headers).json()
    assert report is not None and report["metrics"]["insurance_leads"] == batch


@requires_db
def test_outbound_messages_created_per_account(client, auth_headers):
    """Agents create outbound Message rows; insurance routes via its own mailbox."""
    from app.config import settings
    batch = settings.lead_batch_size

    msgs = client.get("/messages?limit=500", headers=auth_headers).json()
    assert len(msgs) >= 2 * batch  # insurance batch + savorymind batch cold emails

    insurance = [m for m in msgs if m["from_account"] == "insurance"]
    personal = [m for m in msgs if m["from_account"] == "personal"]
    assert len(insurance) == batch          # every insurance lead gets a first touch
    assert len(personal) >= batch           # restaurant prospects (+ any others)
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
def test_cron_endpoint_requires_token(client):
    # No token configured in tests → cron endpoints are locked down.
    assert client.post("/cron/inbound").status_code == 401
    assert client.post("/cron/inbound", headers={"X-Cron-Token": "wrong"}).status_code == 401


@requires_db
def test_social_queue_endpoint(client, auth_headers):
    r = client.get("/outreach/social", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@requires_db
def test_job_apply_queue_and_mark(client, auth_headers):
    # The daily cycle already created jobs; the queue returns pending ones.
    q = client.get("/jobs/queue", headers=auth_headers).json()
    assert isinstance(q, list) and q, "expected queued jobs from the daily run"
    item = q[0]
    assert item["url"] and "title" in item and "score" in item

    # Marking a job 'Applied' removes it from the queue.
    r = client.post("/jobs/queue/mark", headers=auth_headers,
                    json={"job_id": item["job_id"], "status": "Applied"})
    assert r.status_code == 200 and r.json()["ok"] is True
    q2 = client.get("/jobs/queue", headers=auth_headers).json()
    assert all(x["job_id"] != item["job_id"] for x in q2)


@requires_db
def test_csv_import_leads(client, auth_headers):
    csv_data = "email,company_name\njane@acmeplumbing.com,Acme Plumbing\n,No Email Co\n"
    r = client.post("/import/leads", headers=auth_headers,
                    files={"file": ("leads.csv", csv_data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 1 and body["skipped_no_email"] == 1


@requires_db
def test_csv_export(client, auth_headers):
    r = client.get("/export/leads.csv", headers=auth_headers)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "company_name" in r.text.splitlines()[0]  # header row


@requires_db
def test_connections_crud_and_secret_encryption(client, auth_headers):
    # Catalog is available.
    cats = client.get("/connections/providers", headers=auth_headers).json()
    assert any(p["key"] == "instagram" for p in cats)

    # Missing required field is rejected.
    bad = client.post("/connections", headers=auth_headers,
                      json={"provider": "instagram", "credentials": {}})
    assert bad.status_code == 400

    # Connect an account with credentials.
    r = client.post("/connections", headers=auth_headers, json={
        "provider": "instagram", "display_name": "Bruno IG", "goal": "followers",
        "credentials": {"access_token": "secret-token-123", "ig_user_id": "17841400000000000"},
    })
    assert r.status_code == 200
    conn = r.json()
    cid = conn["id"]
    assert conn["provider"] == "instagram" and conn["status"] == "connected"
    # The raw secret is NEVER returned by the API.
    assert "secret-token-123" not in r.text and "credentials" not in conn

    # It's stored encrypted at rest (not plaintext).
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    row = db.query(models.Connection).filter(models.Connection.id == cid).first()
    assert row.credentials_enc and "secret-token-123" not in row.credentials_enc
    from app.security import decrypt_secret
    import json as _json
    assert _json.loads(decrypt_secret(row.credentials_enc))["access_token"] == "secret-token-123"
    db.close()

    # Funnel plan is generated for the connection.
    plan = client.get(f"/connections/{cid}/funnel", headers=auth_headers).json()
    assert plan["provider"] == "instagram" and plan["stages"]

    # Overview aggregates coverage.
    ov = client.get("/connections/overview", headers=auth_headers).json()
    assert ov["connected"] >= 1

    # Disconnect.
    d = client.delete(f"/connections/{cid}", headers=auth_headers)
    assert d.status_code == 200
    assert all(c["id"] != cid for c in client.get("/connections", headers=auth_headers).json())


@requires_db
def test_leads_are_not_duplicated_across_runs(client, auth_headers):
    """A second agent run must not create duplicate leads for the same email."""
    from app import models
    from app.database import SessionLocal
    from app.agents.insurance import InsuranceAgent

    db = SessionLocal()
    before = db.query(models.Lead).count()
    InsuranceAgent(db).run()
    after_first = db.query(models.Lead).count()
    InsuranceAgent(db).run()
    after_second = db.query(models.Lead).count()
    # No new leads on the second run (all emails already exist) — and no dup emails.
    emails = [e for (e,) in db.query(models.Lead.email).filter(models.Lead.email.isnot(None)).all()]
    assert len(emails) == len(set(emails)), "duplicate lead emails found"
    assert after_second == after_first  # second run added nothing new
    assert after_first >= before
    db.close()


@requires_db
def test_outreach_bumps_contact_count():
    # The reach-out counter helper increments count + stamps a time.
    from app import models, outreach
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        lead = models.Lead(segment="commercial", email="touch-test@acme.com",
                           company_name="Touch Co", status="New")
        db.add(lead); db.flush()
        outreach._bump_contact(db, "lead", lead.id)
        outreach._bump_contact(db, "lead", lead.id)
        db.flush()
        assert lead.times_contacted == 2 and lead.last_contacted_at is not None
    finally:
        db.rollback(); db.close()


@requires_db
def test_brand_profile_get_and_update(client, auth_headers):
    p = client.get("/profile", headers=auth_headers).json()
    assert p["business_name"]  # seeded with a default on first read
    r = client.put("/profile", headers=auth_headers,
                   json={"instagram_handle": "brunotest", "niche": "Test niche"})
    assert r.status_code == 200 and r.json()["instagram_handle"] == "brunotest"
    p2 = client.get("/profile", headers=auth_headers).json()
    assert p2["niche"] == "Test niche"  # persisted

    # The brand context used by content agents reflects the saved profile.
    from app import brand
    from app.database import SessionLocal
    db = SessionLocal()
    assert "Test niche" in brand.context(db)
    db.close()


@requires_db
def test_connected_hubspot_drives_crm_token(client, auth_headers):
    """Connecting a HubSpot account makes lead sync use its token over the env var."""
    from app.config import settings
    from app.database import SessionLocal
    from app.integrations import crm

    r = client.post("/connections", headers=auth_headers, json={
        "provider": "hubspot", "display_name": "Bruno CRM",
        "credentials": {"access_token": "pat-from-connection"},
    })
    assert r.status_code == 200
    cid = r.json()["id"]
    db = SessionLocal()
    old = settings.hubspot_api_key
    try:
        settings.hubspot_api_key = "env-key"
        # The connected account's token wins over the env var.
        assert crm.resolve_token(db) == "pat-from-connection"
    finally:
        settings.hubspot_api_key = old
        db.close()
        client.delete(f"/connections/{cid}", headers=auth_headers)


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
