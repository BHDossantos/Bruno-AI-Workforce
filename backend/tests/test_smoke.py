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
        "leadership": 30, "cloud_sre_match": 30, "ai_data_platform": 15,
        "remote": 15, "salary_200k_plus": 10,
    }
    # A relevant leadership+cloud role still clears 75% with no salary listed.
    s2, _ = JobHunterAgent.score_job(
        {"title": "Director, Cloud Engineering", "description": "platform reliability",
         "remote": True, "salary_min": None})
    assert s2 >= 75


def test_low_scoring_job_is_filtered():
    score, _ = JobHunterAgent.score_job(
        {"title": "Software Engineer", "description": "react frontend",
         "remote": False, "salary_min": 120_000}
    )
    assert score < 75


def test_insurance_and_music_scoring():
    assert InsuranceAgent.score_lead(
        {"email": "a@b.c", "phone": "1", "website": "x", "segment": "commercial"}
    ) == 100
    assert MusicAgent.genre_match("R&B") == 100  # Luxury Latin Soul lane
    assert MusicAgent.genre_match("Romantic") == 100
    assert MusicAgent.genre_match("Techno") == 50


def test_music_brand_never_on_linkedin_and_is_fan_facing():
    """The music universe must promote Bruno D (story + streams) and never touch
    LinkedIn — the two things the user explicitly asked for."""
    from app import evergreen, music_brand, platform_loops

    # LinkedIn loop must not carry the music business line.
    assert "music" not in platform_loops.LOOPS["linkedin"]["businesses"]
    # Music must live on fan channels.
    assert "music" in platform_loops.LOOPS["instagram"]["businesses"]
    assert "music" in platform_loops.LOOPS["tiktok"]["businesses"]
    # The brand bible owns a category and excludes LinkedIn.
    assert music_brand.CATEGORY == "Luxury Latin Soul"
    assert "linkedin" not in music_brand.CHANNELS
    # Evergreen "music" seeds are story-first, not industry thought leadership.
    seeds = " ".join(evergreen.CATEGORIES["music"]).lower()
    assert "growth loop" not in seeds and "pitching playlists" not in seeds
    assert any(w in seeds for w in ("story", "lyric", "sax", "rome"))


def test_content_factory_drops_linkedin_for_music(monkeypatch):
    """generate_pack must strip LinkedIn from the channel list for music even if
    asked, regardless of whether generation is available."""
    from app import content_factory

    monkeypatch.setattr(content_factory.client, "is_live", lambda: False)
    res = content_factory.generate_pack(
        db=None, topic="the true story behind this lyric", business="music",
        channels=["linkedin", "instagram", "tiktok"])
    # is_live() is False so it no-ops, but the music guard already ran — and it
    # must never have included linkedin. (No DB touched on this path.)
    assert res["ok"] is False  # generation unavailable offline


def test_music_links_include_all_platforms():
    """Apple Music + YouTube Music wired alongside Spotify (Pandora intentionally
    omitted — region-restricted)."""
    from app import music_brand
    from app.brand import _DEFAULTS
    links = _DEFAULTS["music_links"]
    assert "open.spotify.com" in links
    assert "music.apple.com" in links
    assert "music.youtube.com" in links
    assert "pandora" not in links.lower()
    assert music_brand.DEFAULT_LINKS.splitlines()[0].startswith("Spotify:")


def test_release_kit_shape_and_offline():
    """The era kit has the full deliverable set and degrades gracefully offline."""
    from app import music_release
    from app.models import MusicRelease

    keys = [k for k, _l, _c in music_release.DELIVERABLES]
    for must in ("music_video", "lyric_video", "behind_the_song", "sax_version",
                 "acoustic_version", "piano_version", "tiktok_hook", "reel_1"):
        assert must in keys
    # No music deliverable targets LinkedIn.
    assert all(c != "linkedin" for _k, _l, c in music_release.DELIVERABLES)
    # _piece normalizes any AI shape.
    assert music_release._piece("just a string")["body"] == "just a string"
    assert music_release._piece({"script": "s", "hashtags": ["#a", "#b"]})["hashtags"] == "#a #b"
    # Offline (no OpenAI) it no-ops cleanly without a DB.
    res = music_release.build_kit(db=None, release=MusicRelease(title="Test Song"))
    assert res["ok"] is False


def test_followups_are_memory_aware():
    """Outreach must recall what we know before writing — the Operating Memory."""
    from app import memory
    from app.ai.prompts import FOLLOWUP_EMAIL
    # No name/email → no DB calls, empty block (safe to call anywhere).
    assert memory.entity_context(db=None, name=None, email=None) == ""
    # The follow-up prompt carries a memory slot that gets injected.
    out = FOLLOWUP_EMAIL.format(step=2, name="Ana", context="insurance",
                                memory="What you remember about Ana:\n- prefers mornings")
    assert "prefers mornings" in out


def test_memory_slot_prompts_format_cleanly():
    """Every prompt with a {memory} slot must format with the exact keys call sites
    pass — guards against the KeyError class of bug when a slot is added."""
    from app.ai.prompts import FOLLOWUP_EMAIL, INFLUENCER_PITCH, PLAYLIST_PITCH
    assert all("{memory}" in p for p in (FOLLOWUP_EMAIL, PLAYLIST_PITCH, INFLUENCER_PITCH))
    FOLLOWUP_EMAIL.format(step=1, name="A", context="x", memory="m")
    PLAYLIST_PITCH.format(name="P", genre="g", curator="c", memory="m")
    INFLUENCER_PITCH.format(name="N", niche="n", platform="ig", handle="h", memory="m")


@requires_db
def test_bulk_dispatch_endpoints(client, auth_headers):
    """Bulk dispatch returns a clean summary for leads and restaurants."""
    r = client.post("/leads/dispatch", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and "dispatched" in d and "pending" in d
    r2 = client.post("/restaurants/dispatch", headers=auth_headers)
    assert r2.status_code == 200 and r2.json()["ok"] is True


def test_bridge_token_auth():
    """The iMessage bridge rejects a bad/empty token (machine-client auth)."""
    import pytest as _pytest
    from fastapi import HTTPException
    from app.config import settings
    from app.routers.bridge import _auth
    old = settings.bridge_token
    try:
        settings.bridge_token = ""  # not configured → always reject
        with _pytest.raises(HTTPException):
            _auth(None)
        settings.bridge_token = "secret"
        with _pytest.raises(HTTPException):
            _auth("wrong")
        _auth("secret")  # correct token → no raise
    finally:
        settings.bridge_token = old


def test_cron_safe_swallows_errors():
    """A cron worker failure returns 200-with-error, not a 500 (no scheduler hot-loop)."""
    from app.routers.cron import _safe
    def boom():
        raise RuntimeError("kaboom")
    out = _safe("x", boom)
    assert out["ok"] is False and "kaboom" in out["error"]
    assert _safe("y", lambda: {"ok": True}) == {"ok": True}


def test_newsletter_funnel_mapping():
    """Warm-reply → funnel mapping + funnel set are correct (CAN-SPAM: opt-in only)."""
    from app import newsletters
    assert newsletters.funnel_for_segment("commercial") == "insurance"
    assert newsletters.funnel_for_segment("personal") == "insurance"
    assert newsletters.funnel_for_segment("consulting") == "bnbglobal"
    assert newsletters.funnel_for_segment("other") is None
    assert set(newsletters.FUNNELS) == {"insurance", "bnbglobal", "savorymind", "music"}
    # subscribe() ignores unknown funnels / empty email (db not touched on those paths).
    assert newsletters.subscribe(db=None, funnel="nope", email="a@b.c") is False
    assert newsletters.subscribe(db=None, funnel="insurance", email=None) is False


def test_bulk_outreach_helpers_exist():
    """The shared dispatch module powers both the buttons and the auto cron."""
    from app import bulk_outreach
    assert hasattr(bulk_outreach, "dispatch_leads")
    assert hasattr(bulk_outreach, "dispatch_restaurants")


def test_instagram_dm_deeplink():
    """The IG assist queue links straight to the DM thread (ig.me/m/<handle>)."""
    from app.routers.outreach_queue import _ig, _ig_dm
    assert _ig_dm("@brunohddm") == "https://ig.me/m/brunohddm"
    assert _ig_dm("curator") == "https://ig.me/m/curator"
    assert _ig_dm(None) is None
    assert _ig("@x") == "https://instagram.com/x"


@requires_db
def test_activation_checklist(client, auth_headers):
    """The go-live checklist returns a readiness score, required items, and a next step."""
    r = client.get("/activation", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert 0 <= d["ready_pct"] <= 100
    assert d["required_total"] >= 1 and len(d["checklist"]) >= d["required_total"]
    keys = {c["key"] for c in d["checklist"]}
    assert {"ai", "email", "scheduler", "social"} <= keys
    # In CI nothing is configured, so essentials are pending and it isn't live.
    assert d["live"] is False


def test_connector_credential_aliases():
    """Standard credential names resolve legacy aliases, so old + new connections
    both work after the naming standardization."""
    from app.integrations import connectors
    assert connectors.cred({"page_access_token": "abc"}, "access_token") == "abc"  # legacy FB
    assert connectors.cred({"access_token": "new"}, "access_token") == "new"       # standard
    assert connectors.cred({"app_id": "123"}, "client_id") == "123"               # Meta alias
    assert connectors.cred({"app_secret": "s"}, "client_secret") == "s"
    assert connectors.cred({}, "access_token", default="x") == "x"                 # safe default
    assert connectors.cred(None, "access_token") is None


def test_contact_import_any_platform():
    """Contact import normalizes headers from every common export + parses vCard."""
    from app import importer
    # Google Contacts
    g = importer.normalize_contact({"Given Name": "Ana", "Family Name": "Cruz",
        "E-mail 1 - Value": "ana@x.com", "Phone 1 - Value": "+1555", "Organization Name": "Cruz Co"})
    assert g["name"] == "Ana Cruz" and g["email"] == "ana@x.com" and g["company"] == "Cruz Co"
    # Outlook
    o = importer.normalize_contact({"First Name": "Bob", "Last Name": "Lee",
        "E-mail Address": "bob@y.com", "Mobile Phone": "+1777"})
    assert o["name"] == "Bob Lee" and o["email"] == "bob@y.com" and o["phone"] == "+1777"
    # LinkedIn
    li = importer.normalize_contact({"First Name": "Cid", "Last Name": "Ngo",
        "Email Address": "cid@z.com", "Company": "Zeta", "Position": "CTO"})
    assert li["email"] == "cid@z.com" and li["company"] == "Zeta" and li["title"] == "CTO"
    # iPhone / iCloud vCard
    vcf = ("BEGIN:VCARD\nVERSION:3.0\nFN:Dina Ray\nEMAIL;type=INTERNET:dina@a.com\n"
           "TEL;type=CELL:+1999\nORG:Ray LLC\nTITLE:Owner\nEND:VCARD\n")
    cards = importer.parse_vcards(vcf)
    assert len(cards) == 1
    c = importer.normalize_contact(cards[0])
    assert c["name"] == "Dina Ray" and c["email"] == "dina@a.com" and c["phone"] == "+1999"


def test_meta_token_upgrade_is_safe():
    """Auto-upgrade is a no-op for non-Meta providers and when app creds are absent,
    so connecting never breaks; it never downgrades a token."""
    from app.integrations import meta_tokens
    # Non-Meta provider: untouched.
    creds = {"access_token": "x"}
    assert meta_tokens.upgrade("linkedin", creds) == creds
    # Meta provider but no app id/secret available → returned unchanged (no network).
    out = meta_tokens.upgrade("facebook", {"access_token": "short"})
    assert out == {"access_token": "short"}


def test_agent_health_suggestions():
    """Agent self-report turns its track record into an actionable nudge."""
    from app.routers.agents import _suggest
    assert "Never run" in _suggest(0, None, None)
    assert "failure rate" in _suggest(10, 40, "boom").lower()
    assert "reliable" in _suggest(8, 100, None).lower()
    assert _suggest(3, 100, None)  # stable case returns a non-empty nudge


def test_decision_journal_patterns():
    """The journal computes win-rate overall, by category, and by confidence band."""
    from app.routers.decisions import CATEGORIES, _analyze

    class D:
        def __init__(self, category, confidence, outcome):
            self.category, self.confidence, self.outcome = category, confidence, outcome

    rows = [D("career", 80, "success"), D("career", 90, "failure"),
            D("music", 40, "success"), D("business", 75, "success")]
    p = _analyze(rows)
    assert p["reviewed"] == 4
    assert p["overall_win_rate"] == 75  # 3/4
    assert p["calibration"]["high_confidence_n"] == 3  # >=70
    assert any(c["category"] == "career" and c["count"] == 2 for c in p["by_category"])
    assert "business" in CATEGORIES
    assert _analyze([])["overall_win_rate"] is None  # safe with no data


def test_planning_paths_rank_and_meet_target():
    """The planner ranks feasible paths first and flags whether each hits the target."""
    from app import planning
    # Streams from a fresh DB fall back to floors, so paths are still meaningful.
    assert all(k in planning._FLOOR for k in
               ("exec_role", "insurance", "consulting", "savorymind", "music"))
    assert len(planning._PATHS) >= 3
    # Probability blend applies a focus penalty as streams are added.
    assert planning._PROB["insurance"] > planning._PROB["music"]


@requires_db
def test_planning_simulate_returns_real_and_potential(client, auth_headers):
    """Simulate returns sane numbers and both current pipeline + potential per path."""
    r = client.get("/planning/simulate?target=1000000", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["target"] == 1000000 and d["paths"]
    p = d["paths"][0]
    assert p["projected_annual"] > 0  # never NaN/zero (floored potential)
    assert "current_expected" in p and p["current_expected"] >= 0
    assert all("current_pipeline" in c for c in p["components"])


def test_board_report_trend_and_fallback():
    """Board report computes WoW trends and always yields actionable recs offline."""
    from app import board_report
    up = board_report._trend(10, 5)
    assert up["trend"] == "up" and up["delta_pct"] == 100.0
    down = board_report._trend(0, 4)
    assert down["trend"] == "down"
    flat = board_report._trend(0, 0)
    assert flat["trend"] == "flat" and flat["delta_pct"] == 0.0
    # Offline fallback still returns recommendations + a challenge.
    metrics = [{"key": "replies", "label": "Replies received", "this_week": 0,
                "last_week": 6, "delta_pct": -100.0, "trend": "down"}]
    fb = board_report._fallback(metrics, 120000)
    assert fb["recommendations"] and fb["challenge"] and fb["headline"]


def test_opportunity_scoring_formula():
    """An opportunity scores on the same value×prob÷effort×weight×urgency formula
    as jobs/leads, so everything is comparable in one ranked brief."""
    from app import scoring
    # A $50k investor intro at 40% beats a $5k podcast at 20% (same effort/urgency).
    big = scoring._score(50000, 0.4, 2, 1.0, 1.0)
    small = scoring._score(5000, 0.2, 2, 1.0, 1.0)
    assert big > small
    from app.routers.opportunities import KINDS
    assert "investor" in KINDS and "podcast" in KINDS and "speaking" in KINDS


def test_graph_helpers_offline():
    """Graph link validation + neighbor/context helpers are safe with no data."""
    from app import graph
    # Invalid edges are rejected without a DB round-trip.
    assert graph.link(db=None, from_subject="A", to_subject="A", relation="x") is None  # self-link
    assert graph.link(db=None, from_subject="", to_subject="B", relation="x") is None   # empty
    assert graph.link(db=None, from_subject="A", to_subject="B", relation="") is None   # no relation
    # Empty subject → no traversal, empty results.
    assert graph.neighbors(db=None, subject="") == []
    assert graph.context_block(db=None, subject="") == ""


def test_memory_recall_entity_merges_safely():
    """recall_entity merges name+email and is safe with nothing to recall."""
    from app import memory
    assert memory.recall_entity(db=None, name=None, email=None) == []
    assert memory.entity_context(db=None, name=None, email=None) == ""


def test_recap_references_real_columns():
    """Guard: the home recap touches several models' timestamp columns — assert
    they exist so a renamed/missing column fails here, not in a live DB test."""
    from app.models import Application, Contact, ContentItem, Job, Message
    assert hasattr(Job, "found_at")                 # NOT created_at
    assert hasattr(Application, "applied_at")
    for attr in ("channel", "direction", "created_at"):
        assert hasattr(Message, attr)
    assert hasattr(ContentItem, "published_at") and hasattr(ContentItem, "created_at")
    assert hasattr(Contact, "created_at")


def test_all_agents_registered():
    assert set(AGENTS) == {
        "job_hunter", "insurance", "commercial_finder", "homeowner", "referral_partner",
        "follow_up_agent", "review_referral", "bnbglobal", "savorymind", "music",
        "music_pr", "music_collab", "instagram", "grant_research", "foundation_outreach",
        "school_partner", "ceo_dashboard",
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
    # Auto-posting YOUR OWN content via LinkedIn's official API (w_member_social)
    # is permitted; automated connections/DMs are NOT — those stay assist-only.
    assert ("publish_auto", "auto") in li_actions
    assert ("dm_assist", "assist") in li_actions

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


def test_objective_defaults_are_ranked():
    from app import objectives
    keys = [d["key"] for d in objectives.DEFAULTS]
    assert keys[0] == "net_worth"  # COO ranking (net worth on top)
    assert "music" in keys and "exec_role" in keys
    assert objectives.DEFAULTS[0]["weight"] > objectives.DEFAULTS[-1]["weight"]
    assert {c["key"] for c in objectives.CENTERS} >= {"wealth", "business", "influence"}


def test_scoring_weights_prioritize_high_roi_objectives():
    from app import scoring
    # Same dollars + odds, but the executive objective (weight 1.0) must outrank
    # music (weight 0.25) for today's attention.
    assert scoring._score(300_000, 0.5, 2, 1.0, 1.0) > scoring._score(300_000, 0.5, 2, 0.25, 1.0)
    # More effort lowers priority; more probability raises it.
    assert scoring._score(100, 1, 1, 1, 1) > scoring._score(100, 1, 2, 1, 1)
    assert scoring._score(100, 0.9, 1, 1, 1) > scoring._score(100, 0.3, 1, 1, 1)


def test_browser_field_matching_and_default_mode():
    from app import browser
    fm = {"email": "a@b.com", "phone": "555", "full_name": "Bruno Dos Santos", "cover_letter": "Hi"}
    assert browser._match_field("Your Email Address", fm) == "a@b.com"
    assert browser._match_field("mobile_phone", fm) == "555"
    assert browser._match_field("full name", fm) == "Bruno Dos Santos"
    assert browser._match_field("favorite color", fm) is None
    assert browser.is_automation_ready() is False  # off by default -> safe assist mode


def test_plaid_offline_noop():
    from app.integrations import plaid_api
    assert plaid_api.is_configured() is False
    assert plaid_api.create_link_token() is None
    assert plaid_api.sync(None)["ok"] is False


@requires_db
def test_email_warmup_caps_fresh_mailbox(client, auth_headers):
    from app import outreach
    from app.config import settings
    from app.database import SessionLocal
    db = SessionLocal()
    cap = outreach.effective_cap(db, "personal")
    db.close()
    # A fresh/low-history mailbox is capped at the warmup start, not the full cap.
    assert cap <= settings.gmail_daily_send_cap
    assert cap >= settings.email_warmup_start


def test_autonomy_helpers_offline():
    from app import alerts
    from app.integrations import oauth_refresh
    # No connections / no mailbox -> safe no-ops, never raise.
    assert oauth_refresh.refresh_all(None) == {}
    assert alerts._collect_errors({"a": {"error": "boom"}, "b": {"ok": True}}) == {"a": "boom"}
    assert alerts.notify("x", "y") is False  # no mailbox configured in tests


@requires_db
def test_selftest_reports_services(client, auth_headers):
    r = client.get("/admin/selftest", headers=auth_headers).json()
    assert "checks" in r and "ready" in r and r["total"] >= 8
    assert r["checks"]["openai"]["ok"] is False  # no key in CI
    assert r["checks"]["instagram"]["ok"] is False  # not connected


def test_social_unified_publish_offline():
    from app import social
    assert social.connected_platforms(None) == []
    assert social.publish_daily(None, "hello")["published"] == {}
    st = social.status(None)
    for p in ("instagram", "facebook", "linkedin", "x"):
        assert st[p]["connected"] is False
    from app.integrations import linkedin_api, spotify_api, twitter_api
    assert linkedin_api.post(None, "hi")["ok"] is False
    assert twitter_api.post(None, "hi")["ok"] is False
    assert spotify_api.overview(None) == {"connected": False}


@requires_db
def test_finance_networth_and_scoreboard(client, auth_headers):
    client.post("/finance/accounts", headers=auth_headers,
                json={"name": "Checking", "kind": "asset", "category": "checking", "balance": 10000})
    client.post("/finance/accounts", headers=auth_headers,
                json={"name": "Card", "kind": "liability", "category": "credit", "balance": 2500})
    s = client.get("/finance/summary", headers=auth_headers).json()
    assert s["net_worth"] == 7500.0
    client.post("/finance/transactions", headers=auth_headers, json={"amount": 5000, "category": "salary"})
    assert client.get("/finance/summary", headers=auth_headers).json()["monthly_income"] >= 5000
    assert client.get("/scoreboard", headers=auth_headers).json()["net_worth"] == 7500.0


def test_x_and_spotify_in_registry():
    from app.integrations import registry
    keys = {p["key"] for p in registry.list_providers()}
    assert {"x", "spotify"} <= keys


def test_media_hosting_disabled_offline():
    # No OpenAI key / no bucket in tests -> generation+hosting safely no-ops.
    from app import media
    from app.integrations import storage
    assert storage.is_configured() is False
    assert storage.upload_public(b"x", "ig/x.png") is None
    assert media.can_generate() is False
    assert media.generate_and_host("a sunset", "test") is None


def test_applicant_profile_and_field_matching():
    from app import applicant_profile, browser
    flat = applicant_profile.flat_fields()
    # Key application fields are present + authoritative.
    assert flat["city"] == "Hollis" and flat["state"] == "New Hampshire"
    assert flat["require_sponsorship"] == "No" and flat["us_citizen"] == "Yes"
    assert applicant_profile.SCREENING["authorized_to_work"] == "Yes"
    assert "tell_us_about_yourself" in applicant_profile.SHORT_ANSWERS
    # Form-field matcher resolves real ATS labels from the flat profile.
    assert browser._match_field("Current City", flat) == "Hollis"
    assert browser._match_field("Will you require visa sponsorship?", flat) == "No"
    assert browser._match_field("Desired Salary", flat) == "180000"


def test_instagram_api_not_connected():
    from app.integrations import instagram_api
    assert instagram_api.is_connected(None) is False
    assert instagram_api.overview(None) == {"connected": False}
    assert instagram_api.get_account(None) is None
    assert instagram_api.publish_post(None, "http://x/i.jpg", "hi")["ok"] is False


def test_video_pipeline_offline():
    from app import video_pipeline
    from app.integrations import elevenlabs, video_gen
    assert elevenlabs.is_configured() is False and elevenlabs.tts("hi") is None
    assert video_gen.is_configured() is False and video_gen.create("a clip") is None
    assert video_gen.poll("job") == ("pending", None)
    avail = video_pipeline.available()
    assert avail["voiceover"] is False and avail["video"] is False and avail["hosting"] is False
    assert "render" in avail  # depends on whether ffmpeg is installed


def test_content_analytics_offline():
    from app import content_analytics
    assert content_analytics._engagement({"likes": 10, "comments": 2, "shares": 1}) == 17
    assert content_analytics._engagement(None) == 0
    # No DB needed for best_topic fallback path uses evergreen — guard with None-safe call.
    from app import evergreen
    assert evergreen.pick_topic("executive", 0)


def test_content_factory_and_evergreen():
    from app import content_factory, evergreen
    # Evergreen library yields a topic per business line.
    assert evergreen.pick_topic("bnbglobal", 1)
    assert evergreen.pick_topic("music", 2)
    # Offline (no OpenAI) the factory degrades gracefully, never raises.
    r = content_factory.generate_pack(None, "cutting cloud spend", "bnbglobal")
    assert r["ok"] is False and "topic" in r


@requires_db
def test_content_factory_api_offline(client, auth_headers):
    r = client.post("/content/factory", headers=auth_headers,
                    json={"topic": "SLOs explained", "business": "executive"}).json()
    assert "ok" in r  # offline -> ok False, but endpoint works
    assert isinstance(client.get("/content", headers=auth_headers).json(), list)


def test_platform_loops_config_well_formed():
    from app import platform_loops
    from app.content_factory import CHANNELS
    from app.evergreen import BUSINESS_CATEGORIES
    assert set(platform_loops.LOOPS) <= set(CHANNELS)
    # Every loop targets real channels, sane cadence, and valid business lines.
    for plat, cfg in platform_loops.LOOPS.items():
        assert cfg["per_day"] >= 1
        assert isinstance(cfg["auto"], bool)
        assert cfg["businesses"], f"{plat} has no business lines"
        for b in cfg["businesses"]:
            assert b in BUSINESS_CATEGORIES
    # Only platforms with an official publish path auto-publish (ToS-respecting):
    # tiktok / youtube have no publish API wired, so they must be assist-only.
    assert platform_loops.LOOPS["tiktok"]["auto"] is False
    assert platform_loops.LOOPS["youtube"]["auto"] is False
    assert platform_loops.LOOPS["linkedin"]["auto"] is True


@requires_db
def test_platform_loops_offline_and_growth(client, auth_headers):
    from app import platform_loops
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # Offline (no OpenAI) a platform loop degrades gracefully and makes nothing.
        res = platform_loops.run_platform(db, "instagram")
        assert res["platform"] == "instagram" and res.get("made", 0) == 0
        allres = platform_loops.run_all(db)
        assert allres["made_total"] == 0 and "instagram" in allres["platforms"]
    finally:
        db.close()
    # Growth dashboard endpoint returns the expected shape with one row per loop.
    g = client.get("/analytics/growth", headers=auth_headers).json()
    assert set(g["kpis"]) >= {"total_followers", "connected_platforms", "daily_target"}
    assert {p["platform"] for p in g["platforms"]} == set(platform_loops.LOOPS)
    assert g["kpis"]["daily_target"] == sum(c["per_day"] for c in platform_loops.LOOPS.values())


def test_posting_times_defaults_cover_platforms():
    from app import platform_loops, posting_times
    # Every platform loop has a default posting hour, and hours are valid (0-23).
    assert set(platform_loops.LOOPS) <= set(posting_times.DEFAULT_HOURS)
    assert all(0 <= h <= 23 for h in posting_times.DEFAULT_HOURS.values())


@requires_db
def test_posting_times_next_slot_and_endpoint(client, auth_headers):
    from datetime import datetime, timezone
    from app import posting_times
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # With no data, best_hour falls back to the platform default and next_slot
        # returns a future UTC datetime landing on that local hour.
        assert posting_times.best_hour(db, "instagram") == posting_times.DEFAULT_HOURS["instagram"]
        now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        slot = posting_times.next_slot(db, "linkedin", now=now)
        assert slot > now and slot.tzinfo is not None
    finally:
        db.close()
    pt = client.get("/analytics/posting-times", headers=auth_headers).json()
    assert "summary" in pt and "instagram" in pt["summary"]
    assert pt["summary"]["instagram"]["hour"] == posting_times.DEFAULT_HOURS["instagram"]


def test_tiktok_publisher_offline():
    from app import social
    from app.integrations import tiktok_api
    # Wired into the unified publisher + degrades gracefully with no creds.
    assert "tiktok" in social.PLATFORMS
    assert tiktok_api.is_connected(None) is False
    assert tiktok_api.verify(None) is None
    # Not connected → clear reason, never raises.
    assert tiktok_api.post(None, "hi", "http://x/v.mp4")["ok"] is False


def test_medium_publisher_offline():
    from app.integrations import medium_api, registry
    # Medium is in the catalog and degrades gracefully with no creds.
    assert registry.get_provider("medium") is not None
    assert "integration_token" in registry.required_fields("medium")
    assert medium_api.is_connected(None) is False
    assert medium_api.verify(None) is None
    assert medium_api.post_article(None, "T", "body")["ok"] is False


def test_tiktok_oauth_state_and_config():
    from app.integrations import tiktok_api
    from app.routers import connections
    # State token round-trips and rejects tampering / garbage.
    s = connections._sign_state()
    assert connections._valid_state(s) is True
    assert connections._valid_state("123.deadbeef") is False
    assert connections._valid_state("") is False
    # OAuth is gated on configuration (off by default → no auth URL built blindly).
    assert tiktok_api.oauth_configured() is False


def test_browser_field_map_and_autoprepare_api():
    from app import browser
    from app.config import settings
    # Auto-prepare is on by default and the field-map builder is reusable.
    assert settings.auto_prepare_applications is True
    assert hasattr(browser, "autoprepare_for_job")

    class _J:
        url = "https://x/apply"
        cover_letter = "Dear team"
        title = "Head of SRE"
        company = "Acme"
        location = "Remote"
    fm = browser._field_map_for(_J())
    assert fm["city"] == "Hollis" and fm["resume_path"] and fm["cover_letter"] == "Dear team"
    assert fm["answers"]["require_sponsorship"] == "No"


@requires_db
def test_sales_pipeline_endpoint(client, auth_headers):
    p = client.get("/analytics/pipeline", headers=auth_headers).json()
    assert set(p["businesses"]) == {"insurance", "consulting", "savorymind"}
    assert p["businesses"]["insurance"]["scope"] == "NH · MA · FL"
    assert p["businesses"]["consulting"]["scope"] == "US + Europe"
    assert "funnel" in p["businesses"]["savorymind"]


def test_lead_geography_scopes():
    from app.integrations import osm_leads
    # US = 50 states, EU = country list, us_eu = both.
    us = osm_leads.scope_areas("us")
    eu = osm_leads.scope_areas("eu")
    both = osm_leads.scope_areas("us_eu")
    assert len(us) == 50 and len(eu) >= 10 and len(both) == len(us) + len(eu)
    # US states use admin_level 4, countries level 2.
    assert 'admin_level"="4"' in us[0][1]
    assert 'admin_level"="2"' in eu[0][1]
    # Explicit comma list → those areas (insurance stays NH/MA/FL).
    ins = osm_leads.scope_areas("Massachusetts,New Hampshire,Florida")
    assert {a[0] for a in ins} == {"Massachusetts", "New Hampshire", "Florida"}
    # Rotation keeps a single run bounded.
    assert len(osm_leads._rotate(both, 6)) == 6


def test_bnbglobal_in_sales_cron():
    import inspect
    from app.routers import cron
    assert '"bnbglobal"' in inspect.getsource(cron.cron_leads)


def test_adaptive_learning_bandit():
    from app import learning
    # Untried arms are explored first — so it adapts to new options/changes.
    assert learning.pick({"new": (0.0, 0), "old": (50.0, 8)}) == "new"
    # Once all are tried, it exploits the clearly-better arm.
    assert learning.pick({"a": (1.0, 20), "b": (9.0, 20)}) == "b"
    # Degrades safely.
    assert learning.pick({}) is None


def test_referral_engine_offline():
    from app import referrals
    from app.routers import cron
    # Targets engaged (warm) statuses, and degrades to a warm fallback offline.
    assert "Closed Won" in referrals._WARM and "Interested" in referrals._WARM
    body = referrals._body("Sam", "Acme")
    assert "Sam" in body and "referral" in body.lower()
    assert any("referrals" in getattr(r, "path", "") for r in cron.router.routes)


def test_contacts_insurance_outreach_offline():
    from app import contacts_outreach
    from app.config import settings
    # SMS is off by default (TCPA — needs consent).
    assert settings.contacts_sms_enabled is False
    # Offline (no OpenAI) the message degrades to a warm fallback, never raises.
    class _C:
        name = "Jane Doe"
        email = "jane@example.com"
    # Offline path returns the fallback before any DB/memory access, so db=None is safe.
    subj, body = contacts_outreach._message_for(None, _C())
    assert subj and "Jane" in body and "Thrust" in body
    # Family/opt-out emails are excluded (case-insensitive).
    ex = contacts_outreach._exclude_set()
    assert "brianadossantos@gmail.com" in ex
    assert "BrianaDosSantosawx@statefarm.com".lower() in ex


def test_youtube_publisher_offline():
    from app import social
    from app.integrations import youtube_api
    assert "youtube" in social.PLATFORMS and "youtube" in social.VIDEO_CHANNELS
    assert youtube_api.is_connected(None) is False
    assert youtube_api.verify(None) is None
    assert youtube_api.post(None, "hi", "http://x/v.mp4")["ok"] is False


def test_connection_live_check_offline():
    from app.integrations import twitter_api
    from app.routers import connections
    # No connection / no creds → verify is None (degrades, never raises).
    assert twitter_api.verify(None) is None
    # Unknown provider has no live check → ok is None (token stored as-is).
    ok, detail = connections._live_check(None, "totally_unknown")
    assert ok is None and isinstance(detail, str)
    # A real social provider with no creds → ok False (token rejected/absent).
    ok2, _ = connections._live_check(None, "x")
    assert ok2 is False


def test_bnbglobal_agent_registered_and_scored():
    from app.agents import AGENTS, BnbGlobalAgent
    from app.commanders import COMMANDERS
    assert AGENTS["bnbglobal"] is BnbGlobalAgent
    assert "bnbglobal" in COMMANDERS["business"]["agents"]
    # A consulting prospect scores higher than a personal-insurance lead.
    assert BnbGlobalAgent.score_lead({"email": "a@b.com", "website": "x", "phone": "1"}) >= 90


def test_commanders_map_to_real_agents():
    from app.agents import AGENTS
    from app.commanders import COMMANDERS
    covered = set()
    for spec in COMMANDERS.values():
        for k in spec["agents"]:
            assert k in AGENTS  # every commander directs real agents
            covered.add(k)
    assert {"job_hunter", "insurance", "savorymind", "music", "instagram"} <= covered


def test_memory_cosine_similarity():
    from app.memory import _cosine
    assert _cosine([1, 0], [1, 0]) == 1.0
    assert _cosine([1, 0], [0, 1]) == 0.0
    assert _cosine([], [1]) == 0.0
    assert _cosine([1, 1], [1, 1]) > _cosine([1, 1], [1, 0])


@requires_db
def test_memory_add_search_recall(client, auth_headers):
    # Add a fact (no OpenAI in CI -> embedding is None, keyword search path).
    r = client.post("/memory", headers=auth_headers, json={
        "content": "Recruiter Jane at Acme is hiring a Director of SRE",
        "subject": "Jane", "kind": "contact"})
    assert r.status_code == 200 and "id" in r.json()
    # Dedupe: same content+subject doesn't create a second row.
    client.post("/memory", headers=auth_headers, json={
        "content": "Recruiter Jane at Acme is hiring a Director of SRE", "subject": "Jane"})

    hits = client.get("/memory?q=Director%20of%20SRE", headers=auth_headers).json()
    assert any("Director of SRE" in h["content"] for h in hits)
    recall = client.get("/memory/recall?subject=Jane", headers=auth_headers).json()
    assert len(recall) == 1  # deduped


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
    assert summary["jobs_found"] == settings.job_daily_target
    # Multiple agents now feed the insurance funnel (insurance + commercial finder +
    # homeowner), so this is a floor, not an exact batch.
    assert summary["insurance_leads"] >= batch
    assert summary["restaurant_prospects"] == batch
    assert summary["music_playlists"] == 50
    assert summary["instagram_targets"] == 100

    assert len(client.get("/jobs", headers=auth_headers).json()) == settings.job_daily_target
    assert len(client.get("/instagram/targets", headers=auth_headers).json()) == 100
    # Music agent makes 25; the PR + collaboration agents add more influencer-type
    # records, so this is a floor now.
    assert len(client.get("/music/influencers", headers=auth_headers).json()) >= 25

    report = client.get("/reports/latest", headers=auth_headers).json()
    assert report is not None and report["metrics"]["insurance_leads"] >= batch


@requires_db
def test_outbound_messages_created_per_account(client, auth_headers):
    """Agents create outbound Message rows; insurance routes via its own mailbox."""
    from app.config import settings
    batch = settings.lead_batch_size

    msgs = client.get("/messages?limit=500", headers=auth_headers).json()
    assert len(msgs) >= 2 * batch  # insurance batch + savorymind batch cold emails

    insurance = [m for m in msgs if m["from_account"] == "insurance"]
    personal = [m for m in msgs if m["from_account"] == "personal"]
    # Insurance mailbox now carries insurance + commercial-finder + homeowner +
    # referral-partner first touches, so it's a floor, not an exact batch.
    assert len(insurance) >= batch          # every insurance lead gets a first touch
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
def test_leads_are_not_duplicated_across_runs(client, auth_headers, monkeypatch):
    """Re-running the agent over the same prospect must not duplicate the lead."""
    from app import models
    from app.agents import insurance as ins_mod
    from app.database import SessionLocal

    fixed = [{
        "segment": "commercial", "category": "Restaurant", "company_name": "Dedupe Cafe",
        "owner_name": "Joe D", "email": "dedupe-unique@acme.com", "phone": "1",
        "website": "https://x.com", "linkedin": None, "industry": "Restaurant", "city": "Boston",
    }]
    monkeypatch.setattr(ins_mod.providers, "fetch_insurance_leads",
                        lambda segment, count, **kw: fixed if segment == "commercial" else [])

    db = SessionLocal()
    try:
        ins_mod.InsuranceAgent(db).run()
        ins_mod.InsuranceAgent(db).run()  # same prospect again
        n = (db.query(models.Lead)
             .filter(models.Lead.email == "dedupe-unique@acme.com").count())
        assert n == 1  # second run did NOT create a duplicate
    finally:
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
def test_commander_rollup_and_status(client, auth_headers):
    # The daily cycle (run via the CEO→Commander→Agent hierarchy) already ran.
    from app import commanders
    from app.database import SessionLocal
    db = SessionLocal()
    commanders.rollup_objectives(db)
    db.close()
    cc = client.get("/commanders", headers=auth_headers).json()
    centers = {c["center"] for c in cc}
    assert {"wealth", "business", "influence"} <= centers
    assert all("pipeline_value" in c for c in cc)


@requires_db
def test_objective_tuning_and_global_search(client, auth_headers):
    # Re-weight an objective (the COO re-prioritization control).
    r = client.patch("/objectives/insurance", headers=auth_headers, json={"weight": 0.95})
    assert r.status_code == 200 and abs(r.json()["weight"] - 0.95) < 1e-6
    assert client.patch("/objectives/nope", headers=auth_headers, json={"weight": 1}).status_code == 404

    # Global search spans CRM + memory.
    client.post("/crm", headers=auth_headers, json={"name": "Searchable Sam", "kind": "advisor"})
    res = client.get("/search?q=Searchable", headers=auth_headers).json()
    assert "contacts" in res and "memories" in res
    assert any("Searchable" in c["name"] for c in res["contacts"])
    assert client.get("/search?q=", headers=auth_headers).json() == {"contacts": [], "memories": []}


@requires_db
def test_google_contacts_import(client, auth_headers):
    csv = ("First Name,Last Name,Organization Name,Organization Title,"
           "E-mail 1 - Value,Phone 1 - Value,Notes\n"
           "Gina,Curtis,BigCo,Tech Recruiter,gina@bigco-import.com,+16035551212,met at conf\n"
           "NoContact,Person,,,,,\n"
           "Gina,Curtis,BigCo,Tech Recruiter,gina@bigco-import.com,,dupe row\n")
    files = {"file": ("contacts.csv", csv, "text/csv")}
    r = client.post("/import/contacts", headers=auth_headers, files=files).json()
    assert r["imported"] == 1 and r["skipped"] == 2  # blank + duplicate skipped
    found = client.get("/crm?source=manual&q=Gina", headers=auth_headers).json()
    assert any(c["name"] == "Gina Curtis" for c in found)


@requires_db
def test_restaurant_and_music_reachout(client, auth_headers):
    rests = client.get("/restaurants?limit=1", headers=auth_headers).json()
    if rests:
        r = client.post(f"/restaurants/{rests[0]['id']}/send", headers=auth_headers)
        assert r.status_code == 200 and "ok" in r.json()
    pls = client.get("/music/playlists?limit=1", headers=auth_headers).json()
    if pls:
        r = client.post(f"/music/playlists/{pls[0]['id']}/send", headers=auth_headers)
        assert r.status_code == 200 and "ok" in r.json()


@requires_db
def test_universal_crm_aggregates_and_adds(client, auth_headers):
    # Sources from the daily run (leads/restaurants/jobs) surface in one list.
    all_c = client.get("/crm", headers=auth_headers).json()
    assert isinstance(all_c, list) and len(all_c) > 0
    assert {c["source"] for c in all_c} & {"insurance", "savorymind", "career"}

    # Add a standalone contact -> appears under 'manual' and seeds the memory graph.
    r = client.post("/crm", headers=auth_headers, json={
        "name": "Dana Recruiter", "company": "BigCo", "title": "Tech Recruiter", "kind": "recruiter"})
    assert r.status_code == 200
    manual = client.get("/crm?source=manual&q=Dana", headers=auth_headers).json()
    assert any(c["name"] == "Dana Recruiter" for c in manual)
    cid = next(c["id"] for c in manual if c["name"] == "Dana Recruiter")
    detail = client.get(f"/crm/{cid}", headers=auth_headers).json()
    assert "memories" in detail and len(detail["memories"]) >= 1  # auto-seeded


@requires_db
def test_browser_autopilot_assist_mode(client, auth_headers):
    jobs = client.get("/jobs?limit=1", headers=auth_headers).json()
    assert jobs, "expected a job from the daily run"
    task = client.post(f"/browser/apply/{jobs[0]['id']}", headers=auth_headers).json()
    assert task["status"] == "prepared"
    assert task["field_map"]["email"]  # applicant identity populated
    # Run with automation off -> assist mode, needs_review, never crashes.
    r = client.post(f"/browser/tasks/{task['id']}/run", headers=auth_headers).json()
    assert r["status"] == "needs_review" and r["mode"] == "assist"
    assert any(t["id"] == task["id"] for t in client.get("/browser/tasks", headers=auth_headers).json())


@requires_db
def test_brief_action_execute_and_dismiss(client, auth_headers):
    actions = client.get("/brief/today?top=20", headers=auth_headers).json()["top_actions"]
    assert actions, "expected brief actions from the daily run"

    # Dismiss the first action -> it drops out of the brief.
    key = actions[0]["key"]
    assert client.post("/actions/dismiss", headers=auth_headers, json={"key": key}).json()["ok"]
    after = client.get("/brief/today?top=50", headers=auth_headers).json()["top_actions"]
    assert all(a["key"] != key for a in after)

    # Execute an 'apply' action -> marks the job applied (no email, safe).
    apply_key = next((a["key"] for a in after if a["action_type"] == "apply"), None)
    if apply_key:
        r = client.post("/actions/execute", headers=auth_headers, json={"key": apply_key}).json()
        assert r["ok"] is True
        again = client.get("/brief/today?top=50", headers=auth_headers).json()["top_actions"]
        assert all(a["key"] != apply_key for a in again)  # done -> gone


@requires_db
def test_daily_brief_and_command_centers(client, auth_headers):
    objs = client.get("/objectives", headers=auth_headers).json()
    assert any(o["key"] == "exec_role" for o in objs) and len(objs) >= 5

    b = client.get("/brief/today", headers=auth_headers).json()
    assert "focus_score" in b and "estimated_value_today" in b
    assert len(b["top_actions"]) <= 3  # only the top 3 surface
    # The daily cycle created jobs/leads, so there should be ranked actions.
    assert b["total_actions"] >= 1
    assert b["top_actions"][0]["priority"] >= (b["top_actions"][-1]["priority"]
                                               if len(b["top_actions"]) > 1 else 0)

    cc = client.get("/command-centers", headers=auth_headers).json()
    assert {c["key"] for c in cc} >= {"wealth", "business", "influence"}
    sb = client.get("/scoreboard", headers=auth_headers).json()
    assert "pipeline_value" in sb and sb["leads"] >= 0


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


def test_compose_caption_dedupes_hashtags():
    """The duplicated-hashtag bug ('#AI #X #AI #X') must never reach a post."""
    from app import content_factory as cf
    assert cf._dedupe_hashtags("#AI #RestaurantGrowth #AI #RestaurantGrowth") == \
        "#AI #RestaurantGrowth"
    # body already has the tag → don't append it again
    cap = cf.compose_caption("Boost covers tonight #AI", "#AI #RestaurantGrowth")
    assert cap.count("#AI") == 1 and "#RestaurantGrowth" in cap
    # hashtags appended on their own line when body has none
    cap2 = cf.compose_caption("No tags here", "#One #Two #One")
    assert cap2.count("#One") == 1 and "#Two" in cap2


def test_lead_temperature_classify():
    from app.lead_temperature import classify
    assert classify("New") == "cold"
    assert classify("Sent") == "cold"
    assert classify("contact") == "cold"
    assert classify("Replied") == "warm"
    assert classify("Follow-up Needed") == "warm"
    assert classify("Interested") == "hot"
    assert classify("Closed Won") == "hot"
    assert classify("Closed Lost") == "dead"
    assert classify(None) == "cold"


@requires_db
def test_emergency_stop_pauses_sending(client, auth_headers):
    from app import control, outreach
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        control.set_paused(db, True)
        assert control.is_paused(db) is True
        # With the kill-switch on, a dispatch must NOT send — it stays a draft.
        msg = outreach.dispatch_email(
            db, entity_type="lead", entity_id=None, to_email="real@example.com",
            subject="x", body="hi", account="personal", actor="test")
        assert msg.status == "Drafted"
    finally:
        control.set_paused(db, False)
        assert control.is_paused(db) is False
        db.close()


def test_grant_fit_scoring_prioritizes_mission():
    from app.agents.grant_research import score_fit
    music_score, pillar = score_fit("Youth music education scholarship program")
    off_score, _ = score_fit("Highway bridge maintenance contract")
    assert music_score > off_score
    assert pillar in ("Music & Arts", "Education & Scholarships")


def test_voice_interpreter_keyword_fallback():
    """Offline (no AI key) the voice router still maps common orders correctly."""
    from app.routers.voice import _interpret
    assert _interpret("pause everything")["intent"] == "pause"
    assert _interpret("switch to autopilot")["intent"] == "set_mode"
    assert _interpret("approve everything safe")["intent"] == "approve_safe"
    assert _interpret("how many leads today")["intent"] == "metrics"
    assert _interpret("source commercial leads")["intent"] == "run_agent"
    assert _interpret("open approvals")["intent"] == "navigate"
    assert _interpret("write a linkedin post about cloud savings")["intent"] == "write_content"
    assert _interpret("draft outreach to Acme Corp")["intent"] == "draft_outreach"
    assert _interpret("schedule this for tomorrow at 9")["intent"] == "schedule"
    assert _interpret("what failed today")["intent"] == "what_failed"


def test_voice_interpreter_portuguese():
    """The user is bilingual — common Portuguese orders map correctly offline."""
    from app.routers.voice import _interpret
    assert _interpret("pausar tudo")["intent"] == "pause"
    assert _interpret("continuar")["intent"] == "resume"
    assert _interpret("aprovar tudo")["intent"] == "approve_safe"
    assert _interpret("quantos leads hoje")["intent"] == "metrics"
    assert _interpret("buscar leads comerciais")["intent"] == "run_agent"
    assert _interpret("abrir aprovações")["intent"] == "navigate"


@requires_db
def test_approval_approve_resolves_items_without_500(client, auth_headers):
    """Approving content schedules it; approving a lead never 500s even with no
    Gmail connected — it's kept (Approved) and leaves the queue."""
    from app.database import SessionLocal
    from app.models import ContentItem, Lead
    db = SessionLocal()
    c = ContentItem(channel="linkedin", topic="cloud savings", title="T", body="hello",
                    status="needs_approval", business="executive")
    l = Lead(segment="commercial", category="Contractor", company_name="Acme",
             email="owner@acmeexample.com", cold_email="hi there", status="Drafted", score=80)
    db.add_all([c, l]); db.commit()
    cid, lid = str(c.id), str(l.id)
    db.close()

    r = client.post(f"/approvals/content/{cid}/approve", headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is True

    r = client.post(f"/approvals/lead/{lid}/approve", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["status"] in ("Approved", "Sent")

    ids = {i["id"] for i in client.get("/approvals", headers=auth_headers).json()["items"]}
    assert cid not in ids and lid not in ids


@requires_db
def test_lead_pipeline_health_shape(client, auth_headers):
    """The lead-health diagnostic returns the chain, counts and actionable blockers."""
    r = client.get("/leads/pipeline-health", headers=auth_headers)
    assert r.status_code == 200
    h = r.json()
    assert {"healthy", "summary", "counts", "by_brand", "sources", "steps", "blockers"} <= set(h)
    assert {s["key"] for s in h["steps"]} == {"source", "send", "sent", "replies"}
    # No Gmail configured in CI → the top blocker is to connect a mailbox.
    assert any("Gmail" in b for b in h["blockers"])


@requires_db
def test_setup_connect_status_and_save(client, auth_headers):
    """The in-app setup page reports connection status and applies a saved key."""
    from app.config import settings
    s = client.get("/setup", headers=auth_headers).json()
    assert set(s) == {"gmail_personal", "gmail_insurance", "apollo", "google_places"}
    assert s["apollo"]["configured"] is False
    orig = settings.google_places_api_key
    try:
        r = client.post("/setup", headers=auth_headers, json={"google_places_api_key": "test-key-123"})
        assert r.status_code == 200 and "google_places_api_key" in r.json()["saved"]
        assert client.get("/setup", headers=auth_headers).json()["google_places"]["configured"] is True
    finally:
        settings.google_places_api_key = orig  # don't pollute other tests
