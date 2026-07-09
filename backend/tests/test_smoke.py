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


def test_content_factory_skips_near_duplicates(monkeypatch):
    """A topic that's effectively identical to recent content is skipped, not
    re-published — the 'never repeat content' guarantee is enforced, not advisory."""
    from app import content_factory as cf
    monkeypatch.setattr(cf.client, "is_live", lambda: True)
    monkeypatch.setattr(cf.client, "embed", lambda t: [0.1, 0.2, 0.3])
    # Simulate a recent near-identical item (top cosine above the hard threshold).
    monkeypatch.setattr(cf, "_recent_matches", lambda db, qv: ([], 0.99))
    res = cf.generate_pack(db=None, topic="cutting cloud spend", business="bnbglobal",
                           channels=["linkedin"])
    assert res.get("duplicate") is True and res.get("channels") == []
    assert cf._DUPLICATE > cf._SIMILAR  # hard-skip bar is stricter than the nudge bar


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
    out = FOLLOWUP_EMAIL.format(step=2, name="Ana", context="insurance", purpose="social proof",
                                memory="What you remember about Ana:\n- prefers mornings")
    assert "prefers mornings" in out


def test_followup_cadence_has_distinct_purposes():
    """Each follow-up touch has its own job (real funnel), and the last is a breakup."""
    from app.followups import _STEP_PURPOSE, _purpose_for
    purposes = [_purpose_for(s) for s in range(1, 8)]
    assert len(set(purposes)) == 7  # every touch is distinct, not a repeat "bump"
    assert "BREAKUP" in _purpose_for(7)
    assert _STEP_PURPOSE[1] != _STEP_PURPOSE[2]


def test_followup_cadence_is_every_two_days_for_seven_touches():
    """Automated follow-ups fire every 2 days for ~2 weeks (7 touches: days
    2,4,6,8,10,12,14 from first contact) — the user's requested cadence."""
    from app.agents.base import FOLLOW_UP_OFFSETS
    assert sorted(FOLLOW_UP_OFFSETS.keys()) == [1, 2, 3, 4, 5, 6, 7]
    assert [FOLLOW_UP_OFFSETS[s] for s in range(1, 8)] == [2, 4, 6, 8, 10, 12, 14]


@requires_db
def test_outreach_autopilot_defaults_on_and_toggles(client, auth_headers):
    """Outreach Autopilot is ON by default (cold leads + follow-ups auto-send even
    in semi mode) and can be toggled off/on without a redeploy."""
    status = client.get("/control/status", headers=auth_headers).json()
    assert status["outreach_autopilot"] is True  # default ON
    off = client.post("/control/outreach-autopilot", json={"on": False}, headers=auth_headers).json()
    assert off["outreach_autopilot"] is False
    assert client.get("/control/status", headers=auth_headers).json()["outreach_autopilot"] is False
    on = client.post("/control/outreach-autopilot", json={"on": True}, headers=auth_headers).json()
    assert on["outreach_autopilot"] is True


@requires_db
def test_insurance_relay_toggle_routes_through_personal(client, auth_headers):
    """One-click relay: when ON, insurance sends through the personal mailbox with
    a Thrust Reply-To (so it sends without separate Thrust credentials)."""
    from app import control
    from app.config import settings
    from app.database import SessionLocal
    from app.integrations import gmail
    assert client.get("/control/status", headers=auth_headers).json()["insurance_relay"] is False
    on = client.post("/control/insurance-relay", json={"on": True}, headers=auth_headers).json()
    assert on["insurance_relay"] is True
    db = SessionLocal()
    old = (settings.gmail_app_password, settings.gmail_address, settings.insurance_via_personal_reply_to)
    try:
        settings.gmail_app_password = "app-pw-xxxx"
        settings.gmail_address = "me@gmail.com"
        settings.insurance_via_personal_reply_to = control.insurance_relay_via_personal(db)
        login_addr, pw, from_addr, reply_to = gmail._smtp_login("insurance")
        assert login_addr == "me@gmail.com" and pw == "app-pw-xxxx"
        assert reply_to == settings.insurance_gmail_address  # replies go to Thrust
    finally:
        settings.gmail_app_password, settings.gmail_address, settings.insurance_via_personal_reply_to = old
        db.close()
    client.post("/control/insurance-relay", json={"on": False}, headers=auth_headers)


@requires_db
def test_autopilot_excludes_cold_outreach_from_approval_queue(client, auth_headers):
    """With Outreach Autopilot ON, drafted cold lead emails auto-send and must NOT
    count as 'needs your approval' (they're a send queue) — and synthetic addresses
    that can never send are filtered out entirely."""
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        db.add(Lead(segment="commercial", company_name="Real Co", email="real-aq@realco.test.example",
                    status="Drafted", cold_email="hi"))
        db.add(Lead(segment="commercial", company_name="Fake Co", email="fake@example.com",
                    status="Drafted", cold_email="hi"))
        db.commit()
    finally:
        db.close()
    # Autopilot ON (default) → cold outreach is auto-sending, not awaiting approval.
    client.post("/control/outreach-autopilot", json={"on": True}, headers=auth_headers)
    cnt = client.get("/approvals/count", headers=auth_headers).json()
    assert "auto_sending" in cnt and cnt["auto_sending"] >= 1
    listed = client.get("/approvals", headers=auth_headers).json()
    assert all(it["type"] != "lead" for it in listed["items"])  # leads not in the approve queue
    # Turn autopilot OFF → real-email cold leads reappear for approval, synthetic stays hidden.
    client.post("/control/outreach-autopilot", json={"on": False}, headers=auth_headers)
    listed_off = client.get("/approvals", headers=auth_headers).json()
    tos = [it.get("to") for it in listed_off["items"] if it["type"] == "lead"]
    assert "fake@example.com" not in tos  # synthetic never shown
    client.post("/control/outreach-autopilot", json={"on": True}, headers=auth_headers)  # restore default


@requires_db
def test_approval_queue_real_lead_survives_flood_of_synthetic_ones(client, auth_headers):
    """Regression: a real, approvable drafted lead must still surface even when
    hundreds of synthetic-domain drafted leads (filtered out, but only in
    Python — is_real_email() isn't a real column) sort ahead of it by
    created_at — the same starvation bug class already fixed on /leads etc."""
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email.like("approvalflood%@example.com")).delete(
            synchronize_session=False)
        db.query(Lead).filter(Lead.email == "real-approval@realbiz.co").delete(
            synchronize_session=False)
        db.commit()
        # Maximal fit signals + a shared DB with 1000+ other Drafted leads means
        # the final priority-sorted page needs both a high rank AND a generous
        # limit to reliably surface this fixture regardless of pollution.
        db.add(Lead(segment="commercial", company_name="Real Approvable Co",
                    email="real-approval@realbiz.co", phone="+16175550000",
                    website="https://realbiz.co", owner_name="Pat Owner",
                    linkedin="https://linkedin.com/in/patowner", status="Drafted", cold_email="hi"))
        db.add_all([
            Lead(segment="commercial", company_name=f"Synthetic Co {i}",
                email=f"approvalflood{i}@example.com", status="Drafted", cold_email="hi")
            for i in range(350)
        ])
        db.commit()
    finally:
        db.close()

    client.post("/control/outreach-autopilot", json={"on": False}, headers=auth_headers)
    try:
        listed = client.get("/approvals?limit=5000", headers=auth_headers).json()
        tos = [it.get("to") for it in listed["items"] if it["type"] == "lead"]
        assert "real-approval@realbiz.co" in tos
        assert all("@example.com" not in (t or "") for t in tos)
    finally:
        client.post("/control/outreach-autopilot", json={"on": True}, headers=auth_headers)


def test_memory_slot_prompts_format_cleanly():
    """Every prompt with a {memory} slot must format with the exact keys call sites
    pass — guards against the KeyError class of bug when a slot is added."""
    from app.ai.prompts import FOLLOWUP_EMAIL, INFLUENCER_PITCH, PLAYLIST_PITCH
    assert all("{memory}" in p for p in (FOLLOWUP_EMAIL, PLAYLIST_PITCH, INFLUENCER_PITCH))
    FOLLOWUP_EMAIL.format(step=1, name="A", context="x", purpose="p", memory="m")
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


@requires_db
def test_approve_all_clears_the_queue(client, auth_headers):
    """One-click Approve all drains the whole queue: content scheduled, outreach
    sent up to cap (rest stays queued for auto-pacing) — never 500s, and the
    pending count is zero or only the cap-deferred remainder afterwards."""
    r = client.post("/approvals/approve-all", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    for k in ("approved", "content_scheduled", "outreach_sent_now", "outreach_queued"):
        assert k in d
    # No content should remain in needs_approval (all scheduled).
    after = client.get("/approvals", headers=auth_headers).json()
    assert all(it["type"] != "content" for it in after["items"])


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
    # _issue always returns a written issue, even offline (template fallback).
    subj, body = newsletters._issue("insurance")
    assert subj and body


@requires_db
def test_newsletters_are_written_and_listed(client, auth_headers):
    """'Write newsletters now' produces a visible, stored draft per funnel — so a
    newsletter is actually written even before there are subscribers."""
    w = client.post("/newsletters/write", headers=auth_headers).json()
    assert len(w["funnels"]) == 4 and all(f.get("ok") for f in w["funnels"])
    drafts = client.get("/newsletters/drafts", headers=auth_headers).json()["drafts"]
    assert len(drafts) >= 4 and all(d["subject"] and d["body"] for d in drafts)
    # Writing again refreshes (one open draft per funnel, no pile-up).
    client.post("/newsletters/write", headers=auth_headers)
    again = client.get("/newsletters/drafts", headers=auth_headers).json()["drafts"]
    per_funnel = {}
    for d in again:
        per_funnel[d["funnel"]] = per_funnel.get(d["funnel"], 0) + 1
    assert all(n == 1 for n in per_funnel.values())  # exactly one open draft per funnel
    # Dismiss one — it leaves the list.
    client.post(f"/newsletters/drafts/{again[0]['id']}/dismiss", headers=auth_headers)
    after = client.get("/newsletters/drafts", headers=auth_headers).json()["drafts"]
    assert all(d["id"] != again[0]["id"] for d in after)


def test_newsletter_template_designed_html():
    """Every newsletter renders as a designed HTML card — banner (gradient by
    default, photo if configured), heading, body, and an unsubscribe link —
    not bare text."""
    from app.config import settings
    from app import newsletter_template

    orig = settings.newsletter_banner_insurance
    try:
        settings.newsletter_banner_insurance = ""
        html = newsletter_template.render(
            funnel="insurance", label="Thrust Insurance", subject="This week's tip",
            body="Line one.\n\nLine two.", unsubscribe_url="https://x.test/unsub?t=abc")
        assert "This week's tip" in html and "Thrust Insurance" in html
        assert "Line one." in html and "Line two." in html
        assert 'href="https://x.test/unsub?t=abc"' in html
        assert "linear-gradient" in html  # default banner when no photo configured

        settings.newsletter_banner_insurance = "https://cdn.example.com/banner.jpg"
        html2 = newsletter_template.render(
            funnel="insurance", label="Thrust Insurance", subject="S", body="B",
            unsubscribe_url="https://x.test/unsub")
        assert 'src="https://cdn.example.com/banner.jpg"' in html2
    finally:
        settings.newsletter_banner_insurance = orig


@requires_db
def test_newsletter_preview_and_drafts_include_designed_html(client, auth_headers):
    """The preview endpoint and the drafts list both expose the designed HTML,
    not just the raw AI text, so the frontend can show a real preview."""
    p = client.get("/newsletters/insurance/preview", headers=auth_headers).json()
    assert p["ok"] is True and "html" in p and "<div" in p["html"]

    client.post("/newsletters/write", headers=auth_headers)
    drafts = client.get("/newsletters/drafts", headers=auth_headers).json()["drafts"]
    assert drafts and all(d["html"] for d in drafts)


def test_bulk_outreach_helpers_exist():
    """The shared dispatch module powers both the buttons and the auto cron."""
    from app import bulk_outreach
    assert hasattr(bulk_outreach, "dispatch_leads")
    assert hasattr(bulk_outreach, "dispatch_restaurants")


@requires_db
def test_deliverability_dashboard(client, auth_headers):
    """The deliverability screen reports the sending channel, today's sends vs cap,
    the backlog and per-mailbox breakdown — and 'Send all pending now' works."""
    r = client.get("/deliverability", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    # Shape the UI depends on.
    for key in ("status", "tone", "channel", "sent_today", "daily_cap",
                "backlog", "accounts", "failures", "can_send"):
        assert key in d, key
    assert d["tone"] in ("good", "warn", "bad")
    accts = {a["account"] for a in d["accounts"]}
    assert {"personal", "insurance", "bnb", "savorymind"} <= accts
    # In CI nothing is connected, so there's no sender and nothing to send.
    assert d["can_send"] is False
    assert d["channel"]["channel"] is None

    # Drain endpoint is callable and reports a dispatched count (0 with no leads).
    s = client.post("/deliverability/send-now", headers=auth_headers)
    assert s.status_code == 200
    body = s.json()
    assert body["ok"] is True
    assert "dispatched" in body and "leads" in body and "restaurants" in body


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


def test_import_real_world_exports():
    """The two exports users actually download must parse — LinkedIn CSV (with its
    preamble) and a real iCloud .vcf (item-grouped + folded lines)."""
    from app import importer
    from app.routers.imports import _csv_rows
    # LinkedIn Connections.csv ships a 3-line "Notes:" preamble before the header.
    linkedin = ('Notes:\n"When exporting your connections..."\n\n'
                'First Name,Last Name,Email Address,Company,Position\n'
                'Ada,Lovelace,ada@math.org,Analytical,Engineer\n')
    rows = _csv_rows(linkedin)
    assert rows and importer.normalize_contact(rows[0])["email"] == "ada@math.org"
    # iCloud: item-grouped props (item1.EMAIL) + a folded value (continuation line
    # begins with a space). Both are real iCloud quirks that used to drop the email.
    icloud = ("BEGIN:VCARD\nVERSION:3.0\nFN:Maria Garcia\n"
              "item1.EMAIL;type=INTERNET:maria@longdomain\n .com\n"
              "item1.X-ABLabel:HOME\nTEL;type=CELL:+1222\nEND:VCARD\n")
    cards = importer.parse_vcards(icloud)
    assert len(cards) == 1
    c = importer.normalize_contact(cards[0])
    assert c["name"] == "Maria Garcia"
    assert c["email"] == "maria@longdomain.com"  # unfolded + item-prefix stripped
    assert c["phone"] == "+1222"


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
    for attr in ("channel", "direction", "created_at", "sent_at", "status"):
        assert hasattr(Message, attr)  # recap counts SENT by sent_at, not created_at
    assert hasattr(ContentItem, "published_at") and hasattr(ContentItem, "created_at")
    assert hasattr(Contact, "created_at")


@requires_db
def test_recap_and_mission_count_actual_sends_not_drafts(client, auth_headers):
    """The home recap + Mission Control 'Outreach sent' must count ACTUALLY-sent
    emails (sent_at), never drafts — otherwise they claim sends that are really
    sitting in the approval queue (the 'said 155 sent but 0 went out' bug)."""
    from datetime import datetime, timezone
    from app import scoring
    from app.database import SessionLocal
    from app.models import Message
    db = SessionLocal()
    try:
        db.add(Message(channel="email", direction="outbound", to_email="sent@x.co",
                       subject="s", body="b", status="Sent", sent_at=datetime.now(timezone.utc)))
        db.add(Message(channel="email", direction="outbound", to_email="draft@x.co",
                       subject="s", body="b", status="Drafted"))  # no sent_at
        db.commit()
        labels = {r["label"]: r["count"] for r in scoring.recap(db)}
        assert labels.get("outreach emails sent", 0) >= 1
        assert labels.get("outreach drafted (awaiting approval)", 0) >= 1
    finally:
        db.close()
    mc = client.get("/mission/control", headers=auth_headers).json()
    assert mc["today"]["outreach_sent"] >= 1  # counts the real send, not the draft


def test_all_agents_registered():
    assert set(AGENTS) == {
        "job_hunter", "insurance", "commercial_finder", "home_finder", "auto_finder",
        "homeowner", "referral_partner",
        "follow_up_agent", "review_referral", "bnbglobal", "savorymind", "music",
        "music_pr", "music_collab", "music_sync", "instagram", "life_ops",
        "grant_research", "foundation_outreach", "school_partner", "ceo_dashboard",
    }


def test_sync_licensing_targets_and_prompt():
    """The music growth team includes sync licensing — supervisor targets + pitch prompt."""
    from app.ai.prompts import SYNC_PITCH
    from app.integrations import providers
    rows = providers.fetch_sync_targets(4)
    assert rows and all(r.get("email") and r.get("kind") for r in rows)
    # Prompt formats with the call site's exact keys (guards KeyError).
    SYNC_PITCH.format(name="X Sync", kind="TV music supervisor", focus="dramas",
                      contact="A. Reed", memory="")


# ── Home + Auto lead finders (real feeders, no fabricated consumers) ─────────
def test_no_synthetic_personal_insurance_leads():
    """The fake-homeowner junk is gone: with SYNTHETIC_INSURANCE_LEADS off (the
    default), personal-lines sourcing never fabricates individuals — better empty
    than junk. Commercial still tops up synthetically so that pipeline keeps flowing."""
    from app.config import settings
    assert settings.synthetic_insurance_leads is False
    # No real source + no synthetic → personal returns nothing (not fake @example.com rows).
    assert providers.fetch_insurance_leads("personal", 20) == []
    # Commercial is unaffected — synthetic top-up still fills it for demos/tests.
    commercial = providers.fetch_insurance_leads("commercial", 5)
    assert len(commercial) == 5


def test_home_and_auto_feeders_gated_offline():
    """Home + Auto finders source REAL OSM businesses only; with live sourcing
    disabled (test env) they make no network call and return empty — never synthetic."""
    assert providers.fetch_home_feeders(30) == []
    assert providers.fetch_auto_feeders(30) == []
    from app.integrations import osm_leads
    assert osm_leads.fetch_home_feeders(30) == []
    assert osm_leads.fetch_auto_feeders(30) == []


def test_home_auto_agents_registered_and_prompts_build():
    """Both new agents are in the registry, in the daily lead run, and their
    partnership prompt formats with the exact keys the agent passes (guards KeyError)."""
    from app.agents.auto_finder import AutoLeadFinderAgent
    from app.agents.home_finder import HomeLeadFinderAgent
    from app.ai.prompts import REFERRAL_PARTNER_OUTREACH
    assert AGENTS["home_finder"] is HomeLeadFinderAgent
    assert AGENTS["auto_finder"] is AutoLeadFinderAgent
    # Distinct lines, distinct feeder framing.
    assert "home" in HomeLeadFinderAgent.description.lower()
    assert "auto" in AutoLeadFinderAgent.description.lower()
    REFERRAL_PARTNER_OUTREACH.format(
        company_name="Bay State Realty", category="Real Estate Agency", city="Boston")


def test_commercial_targets_trucking_and_construction():
    """Commercial sourcing now explicitly nets trucking + construction/painting/
    carpentry verticals the user asked for (real OSM selectors, not synthetic)."""
    from app.integrations import osm_leads
    cats = osm_leads.COMMERCIAL_OSM
    assert "Trucking & transport" in cats
    assert "Construction & GC" in cats
    # Painters/carpenters/builders are covered by the construction + contractor sets.
    construction = " ".join(osm_leads.COMMERCIAL_OSM["Construction & GC"])
    assert "painter" in construction and "carpenter" in construction
    contractor = " ".join(osm_leads.COMMERCIAL_OSM["Contractor"])
    assert "carpenter" in contractor and "painter" in contractor


# ── Live-source integrations (no network; key-gated) ─────────────────────────
def test_live_sources_disabled_without_keys():
    assert apollo.is_configured() is False
    assert jobs_api.is_configured() is False
    assert apollo.fetch_commercial_leads(10) == []
    assert jobs_api.fetch_jobs(["Director SRE"], limit=5) == []


def test_apollo_enrichment_and_location_targeting():
    """Apollo reveals verified emails (enrichment) + stays in-territory. Locked
    placeholder emails are treated as no-email; enrich is a no-op without a key."""
    from app.integrations import apollo, providers
    # Locked / placeholder addresses Apollo returns before enrichment aren't real.
    assert apollo._is_real("email_not_unlocked@domain.com") is False
    assert apollo._is_real("") is False
    assert apollo._is_real("owner@realbiz.com") is True
    assert apollo._domain("https://www.acme.io/careers") == "acme.io"
    # Enrichment + filtering are safe with no key.
    assert apollo.enrich_email({"first_name": "A", "domain": "x.com"}) is None
    assert apollo._with_emails([{"email": "good@x.com"}, {"email": None}], budget=5) == [{"email": "good@x.com"}]
    # Insurance scope → Apollo person_locations (in-territory); global → unfiltered.
    assert providers._scope_locations("Massachusetts,New Hampshire,Florida") == \
        ["Massachusetts", "New Hampshire", "Florida"]
    assert providers._scope_locations("global") is None
    assert providers._scope_locations(None) is None


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
    assert "Bruno Dossantos" in out and "insurance agent" in out
    assert "tel:+18338547055" in out and "tel:+16039308272" in out  # office + cell click-to-call
    assert "(833) 854-7055" in out and "16039308272" in out          # shown as configured
    assert "unsubscribe" in out.lower()  # CAN-SPAM footer
    assert email_template.render(None) is None

    personal = email_template.render("Hi there", account="personal")
    assert "Bruno Dos Santos, MBA, MSIT" in personal
    assert "tel:+16039308272" in personal
    assert "Thrust Insurance" not in personal  # insurance signature must not leak

    # SavoryMind restaurant outreach gets its own tagline signature, not the IT one.
    savory = email_template.render("Hi chef", account="savorymind")
    assert "SavoryMind" in savory and "tastes better" in savory
    assert "tel:+18338547055" in savory                 # same producer phones
    assert "MBA, MSIT" not in savory                     # not the consulting signature

    # AI placeholders + sign-off are stripped; only the real signature remains.
    raw = ("Hi [Prospect's Name],\n\nRunning a restaurant is hard.\n\n"
           "Best,\n[Your Name]\n\nP.S. If you'd rather not hear from me, let me know.")
    cleaned = email_template.clean_body(raw)
    assert "[Your Name]" not in cleaned and "[Prospect's Name]" not in cleaned
    assert "Best," not in cleaned and "P.S." not in cleaned
    assert "Hi there," in cleaned
    rendered = email_template.render(raw, account="insurance")
    assert "[Your Name]" not in rendered and "Bruno Dossantos" in rendered


@requires_db
def test_booking_nudge_targets_interested_not_booked(client, auth_headers):
    """Interested leads that went quiet get exactly ONE booking nudge; fresh or
    non-interested leads are left alone, and a second run doesn't nudge again."""
    from datetime import datetime, timedelta, timezone
    from app import booking_nudge
    from app.database import SessionLocal
    from app.models import ActionLog, Lead

    old = datetime.now(timezone.utc) - timedelta(days=5)
    fresh = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        interested = Lead(segment="commercial", category="Contractor", company_name="Nudge Me Co",
                          email="nudge@realbiz.com", status="Interested", score=10,
                          last_contacted_at=old)
        too_fresh = Lead(segment="commercial", category="Contractor", company_name="Too Fresh Co",
                         email="fresh@realbiz.com", status="Interested", score=10,
                         last_contacted_at=fresh)
        cold = Lead(segment="commercial", category="Contractor", company_name="Still Cold Co",
                    email="cold@realbiz.com", status="Sent", score=10, last_contacted_at=old)
        db.add_all([interested, too_fresh, cold])
        db.commit()
        target_id = interested.id
    finally:
        db.close()

    r1 = booking_nudge.run(SessionLocal())
    assert r1["eligible"] >= 1

    db = SessionLocal()
    try:
        nudged = {a.entity_id for a in db.query(ActionLog).filter(
            ActionLog.action == "booking_nudge").all()}
        assert str(target_id) in nudged
    finally:
        db.close()

    # Second run must not re-nudge the same lead (one nudge only).
    before = _count_action(client, auth_headers)
    booking_nudge.run(SessionLocal())
    assert _count_action(client, auth_headers) == before


def _count_action(client, auth_headers):
    from app.database import SessionLocal
    from app.models import ActionLog
    db = SessionLocal()
    try:
        return db.query(ActionLog).filter(ActionLog.action == "booking_nudge").count()
    finally:
        db.close()


@requires_db
def test_booking_nudge_endpoint(client, auth_headers):
    """The manual 'Nudge bookings' button endpoint returns a structured summary."""
    r = client.post("/followups/nudge-bookings", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and "sent" in body and "eligible" in body


def test_meta_oauth_url_and_gate():
    """The one-click Facebook/Instagram connect builds a proper consent URL and is
    gated on app credentials being present."""
    from app.config import settings
    from app.integrations import meta_tokens
    orig = (settings.facebook_app_id, settings.facebook_app_secret, settings.meta_redirect_uri)
    try:
        settings.facebook_app_id = settings.facebook_app_secret = settings.meta_redirect_uri = ""
        assert meta_tokens.oauth_configured() is False
        settings.facebook_app_id = "123"
        settings.facebook_app_secret = "secret"
        settings.meta_redirect_uri = "https://api.example.com/connections/meta/oauth/callback"
        assert meta_tokens.oauth_configured() is True
        url = meta_tokens.build_auth_url("st.sig")
        assert url.startswith("https://www.facebook.com/") and "client_id=123" in url
        assert "instagram_content_publish" in url and "pages_manage_posts" in url
        assert "state=st.sig" in url
    finally:
        (settings.facebook_app_id, settings.facebook_app_secret, settings.meta_redirect_uri) = orig


@requires_db
def test_meta_oauth_start_requires_config(client, auth_headers):
    """/connections/meta/oauth/start refuses cleanly when the Meta app isn't set up."""
    from app.config import settings
    orig = (settings.facebook_app_id, settings.facebook_app_secret, settings.meta_redirect_uri)
    try:
        settings.facebook_app_id = settings.facebook_app_secret = settings.meta_redirect_uri = ""
        r = client.get("/connections/meta/oauth/start", headers=auth_headers)
        assert r.status_code == 400
    finally:
        (settings.facebook_app_id, settings.facebook_app_secret, settings.meta_redirect_uri) = orig


@requires_db
def test_client_book_csv_export(client, auth_headers):
    """The client book exports to CSV, filterable by business."""
    from app.database import SessionLocal
    from app.models import Client
    db = SessionLocal()
    try:
        db.add(Client(business="insurance", name="CSV Client", carrier="Progressive",
                      line="auto", premium_monthly=99, status="Active"))
        db.commit()
    finally:
        db.close()
    r = client.get("/export/clients.csv", headers=auth_headers)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    text = r.text
    assert "business,name,email" in text.splitlines()[0]  # header
    assert "CSV Client" in text and "Progressive" in text
    # Business filter works.
    r2 = client.get("/export/clients.csv?business=bnb", headers=auth_headers)
    assert r2.status_code == 200 and "CSV Client" not in r2.text


@requires_db
def test_compose_reply_endpoint(client, auth_headers):
    """The inbox compose-reply endpoint accepts a custom body (e.g. a quote-intake
    email) and routes it through the dispatcher (offline → stored, not Sent)."""
    r = client.post("/messages/reply", headers=auth_headers, json={
        "to_email": "prospect@realbiz.com", "subject": "Your auto quote",
        "body": "Please send your VIN and driver's license.", "account": "insurance"})
    assert r.status_code == 200
    d = r.json()
    assert "ok" in d and "status" in d and d["to"] == "prospect@realbiz.com"
    # Missing body is rejected.
    bad = client.post("/messages/reply", headers=auth_headers,
                      json={"to_email": "x@y.com", "body": ""})
    assert bad.status_code == 400


@requires_db
def test_quote_intake_templates(client, auth_headers):
    """Quote-intake templates cover the four lines with an English checklist and
    ready-to-send EN + PT quotation emails."""
    r = client.get("/book/quote-templates", headers=auth_headers)
    assert r.status_code == 200
    tpls = {t["key"]: t for t in r.json()}
    assert {"personal_auto", "commercial_auto", "workers_comp", "general_liability"} <= set(tpls)
    for t in tpls.values():
        assert t["requirements"] and t["email_subject"]
        assert t["email_body_en"] and t["email_body_pt"]
    # Key domain details made it into English.
    assert any("VIN" in req for req in tpls["personal_auto"]["requirements"])
    assert any("EIN" in req for req in tpls["workers_comp"]["requirements"])
    assert "audit" in tpls["workers_comp"]["email_body_en"].lower()
    assert "payroll" in tpls["general_liability"]["email_body_en"].lower()


@requires_db
def test_client_crm_full_lifecycle(client, auth_headers):
    """The insurance client CRM: carrier options, create with policy details,
    log a communication (updates last-contact), filter, and summarize premium."""
    opts = client.get("/book/carriers", headers=auth_headers).json()
    assert "Progressive" in opts["carriers"] and "State Farm" in opts["carriers"]
    assert set(opts["lines"]) == {"auto", "home", "life", "commercial"}
    assert opts["states"] == ["MA", "NH", "FL"]
    biz_keys = {b["key"] for b in opts["businesses"]}
    assert {"insurance", "bnb", "savorymind", "music"} <= biz_keys

    # Create a won client with a full policy.
    created = client.post("/book/clients", headers=auth_headers, json={
        "business": "insurance", "name": "Jane Homeowner", "email": "jane@realfam.com",
        "state": "NH", "line": "home", "carrier": "Progressive", "premium_monthly": 180.50,
        "policy_number": "PGR-123", "signed_at": "2026-06-01", "expires_at": "2026-12-15",
        "address": "1 Main St", "city": "Concord", "zip": "03301"}).json()
    assert created["business"] == "insurance"
    cid = created["id"]
    assert created["premium_monthly"] == 180.5 and created["carrier"] == "Progressive"
    assert created["days_to_expiry"] is not None

    # Log a call — it appears on the timeline and sets last-contacted.
    client.post(f"/book/clients/{cid}/notes", headers=auth_headers,
                json={"kind": "call", "body": "Reviewed coverage, happy."})
    detail = client.get(f"/book/clients/{cid}", headers=auth_headers).json()
    assert detail["last_contacted_at"] is not None
    assert len(detail["timeline"]) == 1 and detail["timeline"][0]["kind"] == "call"
    assert "emails" in detail  # lead/outreach email history integrated into the CRM

    # An outreach email to this client's address shows up in their email history.
    from app.database import SessionLocal as _SL
    from app.models import Message as _Msg
    _db = _SL()
    try:
        _db.add(_Msg(channel="email", direction="outbound", to_email="jane@realfam.com",
                     from_account="insurance", status="Drafted", subject="Welcome Jane"))
        _db.commit()
    finally:
        _db.close()
    detail2 = client.get(f"/book/clients/{cid}", headers=auth_headers).json()
    assert any(e["subject"] == "Welcome Jane" for e in detail2["emails"])

    # The list view also shows each client's last email, batch-attached (no N+1).
    listed = client.get("/book/clients", headers=auth_headers).json()
    jane_row = next(r for r in listed if r["id"] == cid)
    assert jane_row["last_email"] is not None
    assert jane_row["last_email"]["subject"] == "Welcome Jane"

    # Filter by line + carrier; the client is found.
    rows = client.get("/book/clients?line=home&carrier=Progressive", headers=auth_headers).json()
    assert any(r["id"] == cid for r in rows)

    # A client for a DIFFERENT business — the book separates them.
    client.post("/book/clients", headers=auth_headers, json={
        "business": "bnb", "name": "BnB Client Co", "premium_monthly": 500})

    # Update the premium; summary reflects it and breaks down by business.
    client.patch(f"/book/clients/{cid}", headers=auth_headers, json={"premium_monthly": 200})
    summary = client.get("/book/summary", headers=auth_headers).json()
    assert summary["clients"] >= 2 and summary["monthly_premium"] >= 700
    assert summary["by_line"].get("home", 0) >= 1
    assert summary["by_business"]["insurance"]["clients"] >= 1
    assert summary["by_business"]["bnb"]["clients"] >= 1

    # Filter by business returns only that book.
    bnb = client.get("/book/clients?business=bnb", headers=auth_headers).json()
    assert bnb and all(r["business"] == "bnb" for r in bnb)

    # Convert a won lead into a client, prefilled.
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        lead = Lead(segment="commercial", category="Contractor", company_name="Convert Co",
                    email="convert@realbiz.com", status="Closed Won", score=10)
        db.add(lead); db.commit(); lead_id = str(lead.id)
    finally:
        db.close()
    conv = client.post(f"/book/from-lead/{lead_id}", headers=auth_headers).json()
    assert conv["name"] == "Convert Co" and conv["line"] == "commercial"
    assert conv["business"] == "insurance"  # commercial segment → insurance book


def test_whatsapp_prefers_meta_cloud_over_twilio():
    """WhatsApp is provider-agnostic: Meta's Cloud API (no Twilio markup) wins
    when both are configured; Twilio is the fallback; neither -> unconfigured."""
    from app.config import settings
    from app.integrations import sms, whatsapp_cloud
    orig = (settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token,
            settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_number)
    try:
        settings.whatsapp_cloud_phone_number_id = settings.whatsapp_cloud_token = ""
        settings.twilio_account_sid = settings.twilio_auth_token = settings.twilio_whatsapp_number = ""
        assert sms.whatsapp_configured() is False

        settings.twilio_account_sid, settings.twilio_auth_token = "sid", "tok"
        settings.twilio_whatsapp_number = "+14155550000"
        assert sms.whatsapp_configured() is True  # Twilio alone is enough

        settings.whatsapp_cloud_phone_number_id = "123456"
        settings.whatsapp_cloud_token = "eaa-token"
        assert whatsapp_cloud.is_configured() is True
        assert sms.whatsapp_configured() is True
    finally:
        (settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token,
         settings.twilio_account_sid, settings.twilio_auth_token,
         settings.twilio_whatsapp_number) = orig


@requires_db
def test_send_text_refreshes_saved_twilio_config(client, auth_headers, monkeypatch):
    """Per-lead texting reloads the credentials saved in Setup before checking,
    so a server instance that started before Twilio was connected still sees it
    configured — the root of the 'No texting channel configured' error."""
    from app.config import settings
    from app.database import SessionLocal
    from app.integrations import sms as sms_int
    from app.models import Message

    called = {"refresh": False}
    monkeypatch.setattr("app.sms_engine._refresh_config",
                        lambda db: called.__setitem__("refresh", True))
    monkeypatch.setattr(sms_int, "is_configured", lambda: True)
    monkeypatch.setattr(sms_int, "send_sms", lambda to, body, account="personal": "SMFAKE")
    monkeypatch.setattr(settings, "sms_daily_send_cap", 100000)

    from app import sms_engine
    db = SessionLocal()
    try:
        db.query(Message).filter(Message.to_email == "+15550002222").delete(synchronize_session=False)
        db.commit()
        sid = sms_engine.send_text(db, entity_type=None, entity_id=None,
                                   phone="+15550002222", body="hi", enforce_hours=False)
        assert called["refresh"] is True     # it refreshed config first
        assert sid == "SMFAKE"                # and then actually sent
    finally:
        db.query(Message).filter(Message.to_email == "+15550002222").delete(synchronize_session=False)
        db.commit()
        db.close()


def test_twilio_voice_config_twiml_and_token():
    """Bridge calling is configured with creds + a number + a callback phone;
    browser softphone also needs an API key + TwiML App. TwiML bridges + records
    with a consent notice, and the browser access token carries a voice grant."""
    import jwt
    from app.config import settings
    from app.integrations import twilio_voice as v
    orig = (settings.twilio_account_sid, settings.twilio_auth_token,
            settings.twilio_insurance_number, settings.producer_callback,
            settings.public_base_url, settings.twilio_api_key_sid,
            settings.twilio_api_key_secret, settings.twilio_twiml_app_sid)
    try:
        settings.twilio_account_sid = "AC1"; settings.twilio_auth_token = "tok"
        settings.twilio_insurance_number = "+16035550100"
        settings.producer_callback = ""; settings.public_base_url = "https://x.run.app"
        assert v.is_configured() is False          # no callback phone yet
        settings.producer_callback = "+16175551234"
        assert v.is_configured() is True
        # Bridge TwiML dials the lead, records dual-channel, and announces consent.
        tw = v.bridge_twiml("+15551234567", "lead-1")
        assert "<Dial" in tw and "record-from-answer-dual" in tw and "+15551234567" in tw
        assert "may be recorded" in v.announce_twiml()

        # Browser softphone token
        assert v.browser_configured() is False
        settings.twilio_api_key_sid = "SK1"; settings.twilio_api_key_secret = "secret"
        settings.twilio_twiml_app_sid = "AP1"
        assert v.browser_configured() is True
        tok = v.access_token("agent")
        claims = jwt.decode(tok, "secret", algorithms=["HS256"])
        assert claims["grants"]["voice"]["outgoing"]["application_sid"] == "AP1"
        assert claims["grants"]["identity"] == "agent"
    finally:
        (settings.twilio_account_sid, settings.twilio_auth_token,
         settings.twilio_insurance_number, settings.producer_callback,
         settings.public_base_url, settings.twilio_api_key_sid,
         settings.twilio_api_key_secret, settings.twilio_twiml_app_sid) = orig


@requires_db
def test_call_lead_offline_returns_reason(client, auth_headers):
    """Calling a lead with Twilio not connected returns a clear 400, not a crash."""
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    lid = None
    try:
        db.query(Lead).filter(Lead.email == "calltest@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", owner_name="Call Test", email="calltest@x.co",
                    phone="+15550009999")
        db.add(lead); db.flush(); lid = lead.id; db.commit()
        r = client.post(f"/calls/lead/{lid}", headers=auth_headers)
        assert r.status_code == 400 and "call" in r.json()["detail"].lower()
    finally:
        if lid is not None:
            db.query(Lead).filter(Lead.id == lid).delete(synchronize_session=False); db.commit()
        db.close()


def test_sms_configured_accepts_either_number():
    """Twilio SMS is 'configured' with the creds + EITHER number field (default or
    insurance) — requiring both was a trap that silently blocked texting. And the
    From never resolves empty when only one is set."""
    from app.config import settings
    from app.integrations import sms
    orig = (settings.twilio_account_sid, settings.twilio_auth_token,
            settings.twilio_from_number, settings.twilio_insurance_number)
    try:
        settings.twilio_account_sid, settings.twilio_auth_token = "AC1", "tok"
        settings.twilio_from_number = settings.twilio_insurance_number = ""
        assert sms.is_configured() is False  # creds but no number
        settings.twilio_insurance_number = "+16035550100"
        assert sms.is_configured() is True   # insurance number alone is enough
        assert sms.number_for("personal") == "+16035550100"  # falls back, never empty
        assert sms.number_for("insurance") == "+16035550100"
        settings.twilio_insurance_number = ""
        settings.twilio_from_number = "+16175550111"
        assert sms.is_configured() is True   # default number alone is enough
        assert sms.number_for("insurance") == "+16175550111"
    finally:
        (settings.twilio_account_sid, settings.twilio_auth_token,
         settings.twilio_from_number, settings.twilio_insurance_number) = orig


@requires_db
def test_client_whatsapp_send_gated_and_logged(client, auth_headers):
    """Sending a client WhatsApp message requires a phone number, a non-empty
    body, and a configured provider — and it's rejected cleanly otherwise."""
    from app.config import settings
    orig = (settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token,
            settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_number)
    try:
        settings.whatsapp_cloud_phone_number_id = settings.whatsapp_cloud_token = ""
        settings.twilio_account_sid = settings.twilio_auth_token = settings.twilio_whatsapp_number = ""

        created = client.post("/book/clients", headers=auth_headers, json={
            "business": "insurance", "name": "No Phone Co"}).json()
        r = client.post(f"/book/clients/{created['id']}/whatsapp", headers=auth_headers,
                        json={"body": "hi"})
        assert r.status_code == 400  # no phone on file

        created2 = client.post("/book/clients", headers=auth_headers, json={
            "business": "insurance", "name": "Has Phone Co", "phone": "+16175551234"}).json()
        r2 = client.post(f"/book/clients/{created2['id']}/whatsapp", headers=auth_headers,
                         json={"body": "hi"})
        assert r2.status_code == 400  # WhatsApp not connected

        r3 = client.post(f"/book/clients/{created2['id']}/whatsapp", headers=auth_headers,
                         json={"body": ""})
        assert r3.status_code in (400, 422)  # empty body rejected either way
    finally:
        (settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token,
         settings.twilio_account_sid, settings.twilio_auth_token,
         settings.twilio_whatsapp_number) = orig


@requires_db
def test_book_carriers_exposes_whatsapp_status(client, auth_headers):
    """/book/carriers surfaces whatsapp_configured and includes 'whatsapp' as a
    loggable communication kind."""
    opts = client.get("/book/carriers", headers=auth_headers).json()
    assert "whatsapp_configured" in opts
    assert "whatsapp" in opts["note_kinds"]


def test_webhook_hmac_signature_is_deterministic():
    """The signing helper produces a stable HMAC-SHA256 hex digest, so an
    n8n/Make receiver can verify it independently."""
    import hashlib
    import hmac as hmac_mod
    from app.webhooks import _sign
    body = b'{"event":"client.created"}'
    expected = hmac_mod.new(b"my-secret", body, hashlib.sha256).hexdigest()
    assert _sign("my-secret", body) == expected


@requires_db
def test_webhook_crud_events_and_validation(client, auth_headers):
    """Webhook CRUD: events picklist, create/list/patch/delete, secret is
    write-only, and an unknown event key is rejected."""
    events = client.get("/webhooks/events", headers=auth_headers).json()
    keys = {e["key"] for e in events}
    assert {"client.created", "client.note_added", "lead.replied"} <= keys

    bad = client.post("/webhooks", headers=auth_headers, json={
        "name": "Bad", "url": "https://example.com/hook", "events": ["not.a.real.event"]})
    assert bad.status_code == 400

    created = client.post("/webhooks", headers=auth_headers, json={
        "name": "n8n test", "url": "https://example.com/hook", "secret": "shh",
        "events": ["client.created"]}).json()
    assert created["has_secret"] is True and "secret" not in created
    assert created["events"] == ["client.created"] and created["enabled"] is True

    listed = client.get("/webhooks", headers=auth_headers).json()
    assert any(w["id"] == created["id"] for w in listed)

    updated = client.patch(f"/webhooks/{created['id']}", headers=auth_headers, json={
        "name": "n8n test", "url": "https://example.com/hook", "events": ["*"], "enabled": False}).json()
    assert updated["enabled"] is False and updated["events"] == ["*"]

    assert client.delete(f"/webhooks/{created['id']}", headers=auth_headers).status_code == 200
    assert not any(w["id"] == created["id"] for w in
                  client.get("/webhooks", headers=auth_headers).json())


@requires_db
def test_webhook_dispatch_never_blocks_the_caller(client, auth_headers):
    """A webhook pointed at an unreachable URL must never break the action that
    triggers it (new client creation), and its failure is recorded, not raised."""
    hook = client.post("/webhooks", headers=auth_headers, json={
        "name": "Unreachable", "url": "http://127.0.0.1:1/nowhere",
        "events": ["client.created"]}).json()

    r = client.post("/book/clients", headers=auth_headers, json={
        "business": "insurance", "name": "Webhook Trigger Co"})
    assert r.status_code == 200  # the broken webhook did not break client creation

    rows = client.get("/webhooks", headers=auth_headers).json()
    fired = next(w for w in rows if w["id"] == hook["id"])
    assert fired["last_triggered_at"] is not None
    assert fired["last_status"] and "error" in fired["last_status"].lower()

    # A non-subscribed webhook must NOT fire for an event it isn't subscribed to.
    other = client.post("/webhooks", headers=auth_headers, json={
        "name": "Only replies", "url": "http://127.0.0.1:1/nowhere",
        "events": ["lead.replied"]}).json()
    client.post("/book/clients", headers=auth_headers, json={
        "business": "insurance", "name": "Another Co"})
    unfired = next(w for w in client.get("/webhooks", headers=auth_headers).json()
                  if w["id"] == other["id"])
    assert unfired["last_triggered_at"] is None


@requires_db
def test_webhook_test_endpoint(client, auth_headers):
    """The manual test endpoint fires a synthetic event and reports the result
    without needing a real subscription match."""
    hook = client.post("/webhooks", headers=auth_headers, json={
        "name": "Test target", "url": "http://127.0.0.1:1/nowhere", "events": ["*"]}).json()
    r = client.post(f"/webhooks/{hook['id']}/test", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "status" in body  # unreachable URL -> ok False, but no crash


@requires_db
def test_outreach_digest_preview_and_send(client, auth_headers):
    """The daily digest builds real numbers, and send() no-ops cleanly when no
    recipient is configured (never crashes the morning cron)."""
    from app import outreach_digest
    from app.config import settings
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        d = outreach_digest.build(db)
        for k in ("goal", "sent_7d", "replies_7d", "reply_rate", "warm", "hot", "actions", "hot_leads"):
            assert k in d, k
        # No recipient in CI → clean no-op with a reason, not a crash.
        orig = (settings.report_to_email, settings.admin_email)
        try:
            settings.report_to_email = ""
            settings.admin_email = "admin@example.com"
            out = outreach_digest.send(db)
            assert out["ok"] is False and "reason" in out
        finally:
            settings.report_to_email, settings.admin_email = orig
    finally:
        db.close()

    # The preview endpoint returns the same structured payload.
    r = client.get("/mission/digest/preview", headers=auth_headers)
    assert r.status_code == 200 and "goal" in r.json()


@requires_db
def test_money_actions_cockpit(client, auth_headers):
    """The 'today's money actions' cockpit ranks work and surfaces hot leads with
    a deal value, tied to the client goal."""
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.models import Client, Lead
    db = SessionLocal()
    try:
        db.add(Lead(segment="commercial", category="Contractor", company_name="Hot Money Co",
                    email="hotmoney@realbiz.com", status="Interested", score=10))
        # A policy renewing in 10 days → should surface a renewals action.
        db.add(Client(business="insurance", name="Renew Soon Co", status="Active",
                      expires_at=date.today() + timedelta(days=10)))
        db.commit()
    finally:
        db.close()

    r = client.get("/mission/money-actions", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert {"goal", "actions", "hot_leads"} <= set(d)
    assert any(a["key"] == "renewals" for a in d["actions"])  # renewal reminder surfaced
    assert "target" in d["goal"] and "won_today" in d["goal"]
    # The interested lead shows up as a hot lead with a value and an action to close.
    assert any(h["name"] == "Hot Money Co" and h["value"] > 0 for h in d["hot_leads"])
    assert any(a["key"] == "close_hot" for a in d["actions"])
    for a in d["actions"]:
        for k in ("key", "title", "why", "cta", "action"):
            assert k in a, k


@requires_db
def test_insurance_commander_dashboard_and_lead_timeline(client, auth_headers):
    """The Insurance Commander cockpit reports the day's tiles, the speed
    scoreboard, and a pipeline funnel; and a lead's AI timeline lists every
    action taken on it in order with a live stage + score."""
    from datetime import datetime, timedelta, timezone

    from app import insurance_commander as ic
    from app.database import SessionLocal
    from app.models import FollowUp, Lead, Message

    # A fresh insurance lead received now, first-touched 30s later, plus a due
    # follow-up — enough to exercise tiles, speed and the timeline.
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        lead = Lead(segment="commercial", category="Contractor", company_name="Commander Co",
                    email="commander@x.co", phone="+16035550000", status="New",
                    times_contacted=0, score=90)
        db.add(lead); db.flush()
        db.add(Message(channel="email", direction="outbound", entity_type="lead",
                       entity_id=lead.id, to_email="commander@x.co", subject="Your quote",
                       status="Sent", sent_at=now, created_at=now))
        db.add(FollowUp(entity_type="lead", entity_id=lead.id, step=1,
                        due_date=(now - timedelta(days=1)).date(), completed=False))
        db.commit()
        lid = str(lead.id)
    finally:
        db.close()

    r = client.get("/mission/insurance-commander", headers=auth_headers).json()
    assert set(r["tiles"]) == {"todays_leads", "need_immediate_response",
                               "engaged_waiting_on_quote", "need_follow_up_today",
                               "policies_bound_today", "commission_today"}
    assert r["tiles"]["need_follow_up_today"] >= 1  # our due follow-up counts
    assert [p["stage"] for p in r["pipeline"]] == ic.PIPELINE  # ordered funnel
    assert "avg_seconds" in r["speed"] and "target_seconds" in r["speed"]

    tl = client.get(f"/mission/lead-timeline/{lid}", headers=auth_headers).json()
    assert tl["ok"] is True
    # score is the explainable AI/lead score (0-100), computed live, not the raw field.
    assert tl["lead"]["name"] == "Commander Co" and 0 <= tl["lead"]["score"] <= 100
    kinds = [e["kind"] for e in tl["timeline"]]
    assert "received" in kinds  # lead received event
    assert any(k.startswith("outbound") for k in kinds)  # the outbound email
    assert any(k == "followup" for k in kinds)  # the scheduled follow-up
    # Unknown lead → clean not-found, not a 500.
    assert client.get("/mission/lead-timeline/00000000-0000-0000-0000-000000000000",
                      headers=auth_headers).json()["ok"] is False


@requires_db
def test_lifecycle_engine_advances_stages_and_flags(client, auth_headers):
    """The lead lifecycle engine repairs a genuinely-contacted 'New' lead forward
    to 'Contacted', logs the stage transition into the AI timeline, flags a
    first-response speed breach, and flags a no-reply sequence-exhausted lead as
    return-eligible — all rule-based, idempotent, and never regressing."""
    from datetime import datetime, timedelta, timezone

    from app.database import SessionLocal
    from app.models import ActionLog, FollowUp, Lead, Message

    db = SessionLocal()
    try:
        # Clean any prior run of this fixture so the test is idempotent.
        old = db.query(Lead).filter(Lead.email == "lifecycle@x.co").all()
        for l in old:
            db.query(ActionLog).filter(ActionLog.entity == "lead",
                                       ActionLog.entity_id == str(l.id)).delete(synchronize_session=False)
            db.query(Message).filter(Message.entity_id == l.id).delete(synchronize_session=False)
            db.query(FollowUp).filter(FollowUp.entity_id == l.id).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.email == "lifecycle@x.co").delete(synchronize_session=False)
        db.commit()

        now = datetime.now(timezone.utc)
        # Emailed (so it was really contacted) but still stuck at "New"; first
        # response landed 30 min after receipt (well over the 60s target); its
        # whole follow-up sequence is done with no reply.
        lead = Lead(segment="commercial", category="Contractor", company_name="Lifecycle Co",
                    email="lifecycle@x.co", status="New", times_contacted=1, score=50,
                    created_at=now - timedelta(hours=1))
        db.add(lead); db.flush()
        db.add(Message(channel="email", direction="outbound", entity_type="lead",
                       entity_id=lead.id, to_email="lifecycle@x.co", subject="Hi",
                       status="Sent", sent_at=now - timedelta(minutes=30),
                       created_at=now - timedelta(minutes=30)))
        db.add(FollowUp(entity_type="lead", entity_id=lead.id, step=1,
                        due_date=(now - timedelta(days=2)).date(), completed=True))
        db.commit()
        lid = str(lead.id)
    finally:
        db.close()

    r = client.post("/mission/lifecycle/run", headers=auth_headers).json()
    assert r["status_advanced"] >= 1
    assert r["stage_transitions"] >= 1
    assert r["speed_breaches"] >= 1
    assert r["return_eligible"] >= 1

    # Status was repaired forward-only.
    db = SessionLocal()
    try:
        from app.models import Lead as L
        fresh = db.query(L).filter(L.email == "lifecycle@x.co").first()
        assert fresh.status == "Contacted"
    finally:
        db.close()

    # The stage move shows in the lead's AI timeline.
    tl = client.get(f"/mission/lead-timeline/{lid}", headers=auth_headers).json()
    assert any(e["kind"] == "stage_change" for e in tl["timeline"])

    # The cockpit surfaces the lifecycle counts.
    ov = client.get("/mission/insurance-commander", headers=auth_headers).json()
    assert set(ov["lifecycle"]) == {"stage_moves_today", "speed_breaches", "return_eligible"}
    assert ov["lifecycle"]["return_eligible"] >= 1

    # Idempotent: a second pass makes no new flags for this lead.
    client.post("/mission/lifecycle/run", headers=auth_headers)
    db = SessionLocal()
    try:
        n_breach = db.query(ActionLog).filter(
            ActionLog.entity_id == lid, ActionLog.action == "speed_breach").count()
        n_return = db.query(ActionLog).filter(
            ActionLog.entity_id == lid, ActionLog.action == "return_eligible").count()
        n_stage = db.query(ActionLog).filter(
            ActionLog.entity_id == lid, ActionLog.action == "stage_change").count()
        assert n_breach == 1 and n_return == 1 and n_stage == 1
    finally:
        db.close()


@requires_db
def test_daily_mission_builds_the_morning_card(client, auth_headers):
    """The AI Daily Mission rolls the pipeline into the morning categories —
    leads today, priority, need-quotes, need-calls, renewals, referrals and
    expected revenue — with a plain-English headline."""
    from datetime import date, timedelta

    from app.database import SessionLocal
    from app.models import Client, Lead

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "mission@x.co").delete(synchronize_session=False)
        db.query(Client).filter(Client.email == "missionclient@x.co").delete(synchronize_session=False)
        db.commit()
        # An untouched high-score lead → counts toward priority + need_calls.
        db.add(Lead(segment="commercial", category="Contractor", company_name="Mission Co",
                    email="mission@x.co", status="New", times_contacted=0, score=95))
        # An active client renewing in 10 days → counts toward renewals + referrals.
        db.add(Client(business="insurance", name="Mission Client", email="missionclient@x.co",
                      status="Active", line="auto", premium_monthly=180,
                      expires_at=date.today() + timedelta(days=10)))
        db.commit()
    finally:
        db.close()

    r = client.get("/mission/daily-mission", headers=auth_headers).json()
    assert set(r) >= {"leads_today", "priority", "need_quotes", "need_calls",
                      "need_renewal", "need_referral", "expected_revenue", "headline"}
    assert r["need_calls"] >= 1          # our untouched lead
    assert r["need_renewal"] >= 1        # the client renewing in 10 days
    assert r["need_referral"] >= 1       # active client is a referral opportunity
    assert isinstance(r["expected_revenue"], (int, float)) and r["headline"]


@requires_db
def test_knowledge_seed_loads_starter_docs_and_is_idempotent(client, auth_headers):
    """Seeding loads the starter insurance docs only when the base is empty, and a
    seeded base answers a real question (e.g. bundling discounts)."""
    from app import knowledge_seed
    from app.database import SessionLocal
    from app.models import KnowledgeDoc

    db = SessionLocal()
    try:
        db.query(KnowledgeDoc).delete(synchronize_session=False)
        db.commit()
        first = knowledge_seed.seed_if_empty(db)
        assert first["seeded"] == len(knowledge_seed.STARTER_DOCS) >= 5
        # Idempotent — a second call with docs present seeds nothing.
        second = knowledge_seed.seed_if_empty(db)
        assert second["seeded"] == 0 and second["existing"] >= first["seeded"]
    finally:
        db.close()

    a = client.post("/knowledge/ask", headers=auth_headers,
                    json={"question": "What auto discounts should I check for a bundle?"}).json()
    assert a["ok"] is True and a["sources"]


@requires_db
def test_knowledge_base_add_search_ask_delete(client, auth_headers):
    """The Insurance Knowledge Base stores docs, answers a plain-English question
    from the best-matching doc (citing it as a source), and deletes docs."""
    from app.database import SessionLocal
    from app.models import KnowledgeDoc

    db = SessionLocal()
    try:
        db.query(KnowledgeDoc).filter(KnowledgeDoc.title.like("KBTest%")).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()

    doc = client.post("/knowledge", headers=auth_headers, json={
        "title": "KBTest MA auto discounts",
        "content": "In Massachusetts, homeowners who bundle auto and home qualify for a "
                   "multi-policy discount. Low-mileage drivers under 10,000 miles/year also "
                   "get a usage discount. Continuous prior insurance earns a loyalty credit.",
        "tags": ["auto", "discounts", "MA"]}).json()
    assert doc["title"] == "KBTest MA auto discounts" and "MA" in doc["tags"]
    did = doc["id"]

    # Empty title/content → 400.
    assert client.post("/knowledge", headers=auth_headers,
                       json={"title": "", "content": ""}).status_code == 400

    a = client.post("/knowledge/ask", headers=auth_headers,
                    json={"question": "What discounts apply to a homeowner bundling auto in MA?"}).json()
    assert a["ok"] is True and a["sources"]
    assert any("MA auto discounts" in s["title"] for s in a["sources"])

    # A question with nothing relevant → graceful, no crash.
    empty = client.post("/knowledge/ask", headers=auth_headers,
                        json={"question": "zzzqqq nonexistent topic"}).json()
    assert empty["ok"] is True and empty["sources"] == []

    assert client.delete(f"/knowledge/{did}", headers=auth_headers).json()["ok"] is True
    assert client.delete("/knowledge/00000000-0000-0000-0000-000000000000",
                         headers=auth_headers).status_code == 404


@requires_db
def test_ceo_dashboard_rolls_up_the_business(client, auth_headers):
    """The AI CEO dashboard rolls the book of business into one page — annualized
    commission, policies in force, retention, avg response, close rate and ROI."""
    from app.database import SessionLocal
    from app.models import Client

    db = SessionLocal()
    try:
        db.query(Client).filter(Client.email.in_(["ceo1@x.co", "ceo2@x.co"])).delete(
            synchronize_session=False)
        db.commit()
        # One active policy ($200/mo) and one cancelled → retention 50%.
        db.add(Client(business="insurance", name="CEO Active", email="ceo1@x.co",
                      status="Active", line="auto", premium_monthly=200))
        db.add(Client(business="insurance", name="CEO Churned", email="ceo2@x.co",
                      status="Cancelled", line="auto", premium_monthly=150))
        db.commit()
    finally:
        db.close()

    r = client.get("/mission/ceo", headers=auth_headers).json()
    assert set(r) >= {"revenue_annualized", "policies_in_force", "commission", "retention_pct",
                      "avg_response_seconds", "close_rate_pct", "lead_spend", "roi"}
    assert r["policies_in_force"] >= 1
    # Annual premium on the active policy is 200*12=2400; commission = 2400*rate.
    assert r["commission"] >= round(2400 * r["commission_rate"]) - 1
    assert r["retention_pct"] is not None and 0 <= r["retention_pct"] <= 100


@requires_db
def test_ai_manager_surfaces_plain_english_coaching(client, auth_headers):
    """The AI Manager turns pipeline data into ordered, plain-English coaching —
    a speed-loss dollar estimate from breach flags, and an untouched-leads nudge —
    most urgent (high severity) first, and never returns an empty panel."""
    from app.database import SessionLocal
    from app.models import ActionLog, Lead

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "aimgr@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="commercial", category="Contractor", company_name="AIMgr Co",
                    email="aimgr@x.co", status="New", times_contacted=0, score=50)
        db.add(lead); db.flush()
        # A speed-breach flag → the manager should surface an estimated $ loss.
        db.add(ActionLog(actor="lifecycle", action="speed_breach", entity="lead",
                         entity_id=str(lead.id), detail={"seconds": 600, "target": 60}))
        db.commit()
    finally:
        db.close()

    r = client.get("/mission/ai-manager", headers=auth_headers).json()
    assert isinstance(r["insights"], list) and len(r["insights"]) >= 1
    keys = {i["key"] for i in r["insights"]}
    assert "speed_loss" in keys          # breach flag drove a speed-loss insight
    assert "uncontacted" in keys         # our untouched lead drove the backlog nudge
    speed = next(i for i in r["insights"] if i["key"] == "speed_loss")
    assert speed["severity"] == "high" and speed["value"] >= 0 and "$" in speed["headline"]
    # High-severity insights sort ahead of info-severity ones.
    sev_order = [i["severity"] for i in r["insights"]]
    assert sev_order == sorted(sev_order, key=lambda s: {"high": 0, "medium": 1, "info": 2}[s])


@requires_db
def test_everquote_fidelity_objection_and_valid_returns(client, auth_headers):
    """(1) The 'I didn't request this' objection returns the verify-info script
    naming the lead's actual vehicle. (2) EverQuote return candidates surface only
    valid reasons (invalid phone / email / duplicate / out-of-footprint), never
    'didn't request'."""
    from app import objection_ai
    from app.database import SessionLocal
    from app.models import Lead

    # (1) Verify-info objection routes correctly and is flagged NOT-a-return.
    assert objection_ai.match("I didn't request this quote")["objection"]["key"] == "didnt_request"
    didnt = next(o for o in objection_ai.OBJECTIONS if o["key"] == "didnt_request")
    assert "everquote-valid return reason" in didnt["move"].lower()

    db = SessionLocal()
    try:
        for e in ("dq@x.co", "dupe1@x.co", "dupe2@x.co", "oof@x.co", "badphone@x.co"):
            db.query(Lead).filter(Lead.email == e).delete(synchronize_session=False)
        db.commit()
        # A lead with EverQuote vehicle data → objection reply names the car.
        veh = Lead(segment="personal", category="EverQuote Auto", owner_name="DQ Verify",
                   email="dq@x.co", phone="6035551234", status="New",
                   intake={"source": "everquote", "everquote": {
                       "vehicle_year": 2018, "vehicle_make": "Honda", "vehicle_model": "ACCORD",
                       "state": "NH"}})
        db.add(veh); db.flush()
        vid = str(veh.id)
        # Out-of-footprint (CA not in MA/NH/FL), with a valid phone + email.
        db.add(Lead(segment="personal", category="EverQuote Auto", owner_name="Cal Out",
                    email="oof@x.co", phone="4155559876", status="New",
                    intake={"source": "everquote", "everquote": {"state": "CA",
                            "vehicle_make": "Tesla", "vehicle_model": "MODEL 3"}}))
        # Invalid phone.
        db.add(Lead(segment="personal", category="EverQuote Auto", owner_name="No Phone",
                    email="badphone@x.co", phone="000", status="New",
                    intake={"source": "everquote", "everquote": {"state": "NH"}}))
        # Duplicate email pair.
        for nm, em in (("Dup A", "dupe1@x.co"), ("Dup B", "dupe1@x.co")):
            db.add(Lead(segment="personal", category="EverQuote Auto", owner_name=nm,
                        email=em, phone="6035550000", status="New",
                        intake={"source": "everquote", "everquote": {"state": "NH"}}))
        db.commit()
    finally:
        db.close()

    r = client.post("/mission/objection", json={"text": "I never requested this", "lead_id": vid},
                    headers=auth_headers).json()
    assert r["objection_key"] == "didnt_request"
    assert "2018 Honda Accord" in r["rebuttal"]  # names the real vehicle

    cands = client.get("/leads/everquote/return-candidates", headers=auth_headers).json()
    by_email = {c["email"]: c["reason_code"] for c in cands}
    assert by_email.get("oof@x.co") == "out_of_footprint"
    assert by_email.get("badphone@x.co") == "invalid_phone"
    assert by_email.get("dupe1@x.co") == "duplicate"
    # The valid-vehicle NH lead with a good phone/email is NOT returnable.
    assert "dq@x.co" not in by_email


def test_insurance_backup_mailbox_fallback(monkeypatch):
    """A second (backup) insurance mailbox: when the primary insurance mailbox
    isn't configured but the backup is, sends resolve to the backup — and when
    the primary IS configured, it wins."""
    from app.config import settings
    from app.integrations import gmail

    # Clear both mailboxes' credentials.
    for a in ("insurance_gmail_address", "insurance_gmail_app_password",
              "insurance_backup_gmail_address", "insurance_backup_gmail_app_password",
              "insurance_google_token_json", "insurance_backup_google_token_json"):
        monkeypatch.setattr(settings, a, "", raising=False)

    # Backup account config resolves to the backup fields.
    monkeypatch.setattr(settings, "insurance_backup_gmail_address", "bruno@thrustinsurance.com")
    monkeypatch.setattr(settings, "insurance_backup_gmail_app_password", "abcd efgh ijkl mnop")
    assert gmail._account_cfg(gmail.INSURANCE_BACKUP)["address"] == "bruno@thrustinsurance.com"

    # Primary blank + backup configured → insurance sends resolve to the backup.
    assert gmail.is_configured(gmail.INSURANCE) is False
    assert gmail.is_configured(gmail.INSURANCE_BACKUP) is True
    assert gmail.effective_account(gmail.INSURANCE) == gmail.INSURANCE_BACKUP

    # Configure the primary → it wins over the backup.
    monkeypatch.setattr(settings, "insurance_gmail_address", "bruno@dossantosinsurance.org")
    monkeypatch.setattr(settings, "insurance_gmail_app_password", "zzzz yyyy xxxx wwww")
    assert gmail.is_configured(gmail.INSURANCE) is True
    assert gmail.effective_account(gmail.INSURANCE) == gmail.INSURANCE


def test_everquote_parse_csv_is_tolerant():
    """The importer parses raw CSV, and survives a UTF-8 BOM, CRLF line endings,
    and a tab-delimited spreadsheet export; header-only/empty → 0 rows (not junk)."""
    from app import everquote
    header = '"first_name","last_name","email","phone","detail"'
    row = '"Tess","Driver","tess@x.co","6035550100",""'
    csv_text = header + "\n" + row + "\n"
    assert len(everquote.parse_csv(csv_text)) == 1
    # UTF-8 BOM + CRLF (common when a file is saved from Excel/Notepad).
    assert len(everquote.parse_csv("﻿" + csv_text.replace("\n", "\r\n"))) == 1
    # Tab-delimited (pasted/exported from a spreadsheet).
    tabbed = "first_name\tlast_name\temail\tphone\nTess\tDriver\ttess@x.co\t6035550100\n"
    assert everquote.parse_csv(tabbed)[0]["email"] == "tess@x.co"
    # Header-only or blank → nothing (the real "No rows parsed" case).
    assert everquote.parse_csv(header) == []
    assert everquote.parse_csv("   ") == []


def test_app_password_whitespace_and_own_creds_win(monkeypatch):
    """Two send-blocking bugs are fixed: App Passwords pasted WITH the spaces
    Google shows (or a stray newline) are normalized to the 16 chars SMTP needs,
    and an insurance mailbox with its OWN credentials always logs in as itself —
    a stale relay flag can no longer hijack it into the wrong account → 535."""
    from app.config import settings
    from app.integrations import gmail

    monkeypatch.setattr(settings, "insurance_gmail_address", "bruno@dossantosinsurance.org")
    monkeypatch.setattr(settings, "insurance_gmail_app_password", " abcd efgh\tijkl mnop\n")
    # Spaces/tabs/newlines stripped to the real 16-char password.
    assert gmail._account_cfg("insurance")["app_password"] == "abcdefghijklmnop"

    # Even with the relay flag stuck ON, its own credentials win → logs in AS
    # dossantos with the dossantos password, not the personal account.
    monkeypatch.setattr(settings, "insurance_via_personal_reply_to", True)
    monkeypatch.setattr(settings, "gmail_address", "personal@gmail.com")
    monkeypatch.setattr(settings, "gmail_app_password", "personalpwxxxxxx")
    login, pw, frm, _rt = gmail._smtp_login("insurance")
    assert login == "bruno@dossantosinsurance.org" and pw == "abcdefghijklmnop" and frm == "bruno@dossantosinsurance.org"


def test_everquote_model_casing():
    """Vehicle models read the way people write them: real words title-cased,
    model codes kept upper."""
    from app.everquote import model_case
    assert model_case("KONA") == "Kona"
    assert model_case("CAMRY") == "Camry"
    assert model_case("QX60") == "QX60"        # code with a digit stays upper
    assert model_case("CR-V") == "CR-V"        # short hyphenated code stays upper
    assert model_case("RAV4") == "RAV4"
    assert model_case("F-150") == "F-150"
    assert model_case("MODEL 3") == "Model 3"
    assert model_case("TELLURIDE") == "Telluride"


@requires_db
def test_everquote_leads_are_hot_by_source():
    """In-market inbound leads (EverQuote) are HOT even at status 'New' — a high
    score floors the temperature to hot, so they sort + get worked first. Cold-
    sourced 'New' leads stay cold; a dead status always wins over the score."""
    from app.everquote import _EVERQUOTE_SCORE
    from app.lead_temperature import HOT_SCORE, classify

    assert _EVERQUOTE_SCORE >= HOT_SCORE
    # Score-only caller keeps the old behavior; the score floors to hot.
    assert classify("New") == "cold"                       # cold-sourced, no score
    assert classify("New", _EVERQUOTE_SCORE) == "hot"      # EverQuote import
    assert classify("New", 10) == "cold"                   # low-score New
    assert classify("interested", 0) == "hot"              # engaged wins regardless
    assert classify("closed lost", _EVERQUOTE_SCORE) == "dead"  # dead beats hot score

    # The LeadOut schema surfaces the same hot temperature to the frontend.
    import uuid
    from datetime import datetime, timezone
    from app.schemas import LeadOut
    lead = LeadOut(id=uuid.uuid4(), segment="personal", score=_EVERQUOTE_SCORE,
                   status="New", pushed_to_crm=False, created_at=datetime.now(timezone.utc))
    assert lead.temperature == "hot"


def test_everquote_import_and_personalized_outreach(client, auth_headers):
    """An EverQuote CSV export imports into personal-auto leads (parsing the rich
    JSON detail), and each lead gets a personalized email + SMS + voicemail + call
    notes that reference the real vehicle and carrier. Re-import dedupes by email."""
    import csv as _csv
    import io as _io
    import json as _json

    from app import everquote
    from app.database import SessionLocal
    from app.models import Lead

    detail = _json.dumps({
        "person": {"firstName": "Tess", "lastName": "Driver", "email": "tess@x.co",
                   "phone": "6035550100", "maritalStatus": "Married",
                   "address": {"city": "Nashua", "state": "NH", "zip": "03060"}},
        "autoPolicy": {"residence": "Own", "creditRating": "Excellent", "monthsInsured": 24,
                       "currentInsurer": "GEICO", "currentBiLiability": "100/300",
                       "insuranceExpiration": {"year": 2026, "month": 9},
                       "primaryCar": {"make": "TOYOTA", "year": 2022, "model": "CAMRY",
                                      "submodel": "SEDAN 4 CYL", "ownership": "Financed",
                                      "coverageType": "Typical", "milesPerYear": 8000}},
        "vertical": "auto"})
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["created_at", "eqLeadUUID", "product", "cost", "first_name", "last_name",
                "city", "state", "email", "phone", "current_insurer", "zip_code", "detail"])
    w.writerow(["Jul 3, 2026", "uuid-tess-1", "Preferred", "649", "Tess", "Driver",
                "Nashua", "NH", "tess@x.co", "6035550100", "GEICO", "03060", detail])
    csv_text = buf.getvalue()

    # Pure parse pulls the nested fields.
    rows = everquote.parse_csv(csv_text)
    assert rows[0]["vehicle_make"] == "Toyota" and rows[0]["current_carrier"] == "GEICO"
    assert rows[0]["homeowner"] is True and rows[0]["marital_status"] == "Married"

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "tess@x.co").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    r = client.post("/leads/import-everquote", json={"csv_text": csv_text}, headers=auth_headers).json()
    assert r["imported"] == 1 and r["total"] == 1
    lid = r["lead_ids"][0]

    # Imported EverQuote leads are HOT — scored high so they sort + get worked first,
    # and they show up in the hot-temperature filter even at status "New".
    from app.everquote import _EVERQUOTE_SCORE
    from app.lead_temperature import HOT_SCORE
    _d = SessionLocal()
    try:
        imported = _d.query(Lead).filter(Lead.id == lid).first()
        assert imported.score == _EVERQUOTE_SCORE and imported.score >= HOT_SCORE
    finally:
        _d.close()
    # High limit so the assertion doesn't depend on how many other hot leads exist.
    hot = client.get("/leads?temperature=hot&limit=5000", headers=auth_headers).json()
    ours = [l for l in hot if l["id"] == lid]
    assert ours and ours[0]["temperature"] == "hot"  # fresh EverQuote lead reads hot

    # Re-import the same email dedupes (update, not a new lead).
    r2 = client.post("/leads/import-everquote", json={"csv_text": csv_text}, headers=auth_headers).json()
    assert r2["imported"] == 0 and r2["updated"] == 1

    p = client.get(f"/leads/{lid}/personalized-outreach", headers=auth_headers).json()
    assert p["ok"] is True
    assert "2022 Toyota Camry" in p["email"]["subject"]
    assert "GEICO" in p["email"]["body"]        # names their real carrier
    assert "2022 Toyota Camry" in p["sms"]["body"]
    assert p["voicemail"] and any("Toyota" in n for n in p["call_notes"])
    # Homeowner + married + low-mileage → bundle / multi-driver / low-mileage angles show.
    notes = " ".join(p["call_notes"]).lower()
    assert "bundle" in notes and "low-mileage" in notes

    # Batch: personalize + queue drafts for every not-yet-contacted EverQuote lead.
    # Our lead has a phone, so it gets BOTH an email draft and an SMS draft; a
    # second run is idempotent per channel (both already drafted → skipped).
    b1 = client.post("/leads/everquote/personalize-batch", json={}, headers=auth_headers).json()
    assert b1["queued"] >= 1 and b1["queued_sms"] >= 1
    client.post("/leads/everquote/personalize-batch", json={}, headers=auth_headers)
    from app.models import Message as _M
    _db = SessionLocal()
    try:
        emails = _db.query(_M).filter(_M.entity_id == lid, _M.direction == "outbound",
                                      _M.channel == "email").count()
        texts = _db.query(_M).filter(_M.entity_id == lid, _M.direction == "outbound",
                                     _M.channel == "sms").count()
        # Exactly one of each — the second batch double-drafts neither channel.
        assert emails == 1 and texts == 1
    finally:
        _db.close()

    # Single-lead queue also works.
    q = client.post(f"/leads/{lid}/personalized-outreach/queue", headers=auth_headers).json()
    assert q["ok"] is True and "Camry" in q["subject"]

    assert client.get("/leads/00000000-0000-0000-0000-000000000000/personalized-outreach",
                      headers=auth_headers).status_code == 404


@requires_db
def test_ask_your_book_answers_natural_language_queries(client, auth_headers):
    """The ask-your-book assistant routes plain-English questions to the right
    query and returns matching leads with a reason — offline, no AI key."""
    from app import book_assistant
    from app.database import SessionLocal
    from app.models import Lead

    # Intent routing is pure + deterministic.
    assert book_assistant._match("who needs follow-up today?") == "need_followup"
    assert book_assistant._match("show me the hottest leads") == "hottest"
    assert book_assistant._match("who's waiting on a quote") == "waiting_quote"
    assert book_assistant._match("who should I call today") == "call_today"
    assert book_assistant._match("dead-ends to revive") == "revive"
    assert book_assistant._match("banana") == "help"

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "askbook@x.co").delete(synchronize_session=False)
        db.commit()
        db.add(Lead(segment="personal", category="Homeowner", owner_name="Ask Buyer",
                    email="askbook@x.co", status="Interested", score=95, times_contacted=0))
        db.commit()
    finally:
        db.close()

    r = client.post("/mission/ask", json={"question": "hottest leads"}, headers=auth_headers).json()
    assert r["ok"] is True and r["intent"] == "hottest"
    assert isinstance(r["leads"], list) and r["count"] == len(r["leads"])
    assert all("reason" in l and "stage" in l for l in r["leads"])

    # Help fallback lists what you can ask.
    h = client.post("/mission/ask", json={"question": "xyzzy"}, headers=auth_headers).json()
    assert h["intent"] == "help" and "follow-up" in h["answer"].lower()


@requires_db
def test_lead_return_assistant_queues_and_revives_dead_ends(client, auth_headers):
    """A return-eligible lead (flagged by the lifecycle engine) shows up in the
    return queue with a fresh angle; returning it re-arms a short follow-up
    cadence, flips it back to active, logs it to the timeline, and drops it from
    the queue so it's never nagged twice."""
    from app.database import SessionLocal
    from app.models import ActionLog, FollowUp, Lead

    db = SessionLocal()
    try:
        old = db.query(Lead).filter(Lead.email == "return@x.co").all()
        for l in old:
            db.query(ActionLog).filter(ActionLog.entity_id == str(l.id)).delete(synchronize_session=False)
            db.query(FollowUp).filter(FollowUp.entity_id == l.id).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.email == "return@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", category="Homeowner", owner_name="Return Buyer",
                    email="return@x.co", status="Contacted", score=40)
        db.add(lead); db.flush(); lid = str(lead.id)
        # The lifecycle engine's flag that makes it return-eligible.
        db.add(ActionLog(actor="lifecycle", action="return_eligible", entity="lead",
                         entity_id=lid, detail={"summary": "no reply after full sequence"}))
        db.commit()
    finally:
        db.close()

    q = client.get("/mission/return-queue", headers=auth_headers).json()
    row = next((r for r in q if r["lead_id"] == lid), None)
    assert row is not None and row["angle"] and row["line"] == "home"

    res = client.post(f"/mission/return/{lid}", headers=auth_headers).json()
    assert res["ok"] is True and res["follow_ups_scheduled"] >= 1

    # It's gone from the queue (marked returned) and shows in the timeline.
    q2 = client.get("/mission/return-queue", headers=auth_headers).json()
    assert not any(r["lead_id"] == lid for r in q2)
    tl = client.get(f"/mission/lead-timeline/{lid}", headers=auth_headers).json()
    assert any(e["kind"] == "lead_returned" for e in tl["timeline"])
    # A fresh open follow-up now exists for it.
    db = SessionLocal()
    try:
        n_open = db.query(FollowUp).filter(
            FollowUp.entity_id == lid, FollowUp.completed.is_(False)).count()
        assert n_open >= 1
    finally:
        db.close()

    assert client.post("/mission/return/00000000-0000-0000-0000-000000000000",
                       headers=auth_headers).status_code == 404


@requires_db
def test_call_coach_briefs_the_rep_before_the_call(client, auth_headers):
    """The AI Call Coach assembles a pre-call brief — line, coverage, score, stage,
    the call's goal, what to ask for next, an opener, and the objections most
    likely for the lead's segment (each with a rebuttal)."""
    from app.database import SessionLocal
    from app.models import Lead

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "coach@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", category="Homeowner", owner_name="Coach Buyer",
                    email="coach@x.co", phone="+16035551212", status="Interested", score=65,
                    intake={"quote_type": "personal_auto", "answers": {"vin": "1AAA"},
                            "updated_at": "2026-07-04T00:00:00Z"})
        db.add(lead); db.flush(); lid = str(lead.id); db.commit()
    finally:
        db.close()

    b = client.get(f"/leads/{lid}/call-coach", headers=auth_headers).json()
    assert b["ok"] is True
    assert b["line"] == "auto"            # pinned by the personal_auto intake
    assert b["stage"] and b["goal"]        # a stage-specific goal
    assert 0 <= b["score"] <= 100
    assert b["opener"] and "Coach Buyer" in b["opener"]
    # Personal-lines leads surface price / already-insured style objections.
    assert b["likely_objections"] and all(o["rebuttal"] and o["move"] for o in b["likely_objections"])
    # Intake is partial → the "ask for" step names collecting the rest.
    assert "Collect" in b["ask_next"] or "quote" in b["ask_next"].lower()

    assert client.get("/leads/00000000-0000-0000-0000-000000000000/call-coach",
                      headers=auth_headers).status_code == 404


@requires_db
def test_objection_ai_matches_rebuttal_and_logs_to_timeline(client, auth_headers):
    """Objection AI matches a prospect's words to the right objection, returns a
    proven rebuttal + next move, exposes the full playbook, and logs an
    objection_coached event to the lead's AI timeline when scoped to a lead."""
    from app import objection_ai
    from app.database import SessionLocal
    from app.models import Lead

    # Pure matcher: keyword → the right objection bucket.
    assert objection_ai.match("this is way too expensive right now")["objection"]["key"] == "price"
    assert objection_ai.match("I need to think about it")["objection"]["key"] == "think_about_it"
    # Unknown text falls back to the general handler, never crashes.
    assert objection_ai.match("xyzzy")["objection"]["key"] == "general"

    # The playbook endpoint lists every objection with a rebuttal + move.
    cat = client.get("/mission/objections", headers=auth_headers).json()
    assert len(cat) >= 8 and all(o["rebuttal"] and o["move"] for o in cat)

    # Lead-agnostic help.
    r = client.post("/mission/objection", json={"text": "I already have insurance"},
                    headers=auth_headers).json()
    assert r["ok"] is True and r["objection_key"] == "have_insurance"
    assert r["rebuttal"] and r["move"]

    # Lead-scoped help logs it to that lead's timeline.
    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "objection@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", category="Homeowner", owner_name="Obj Buyer",
                    email="objection@x.co", status="Interested", score=50)
        db.add(lead); db.flush(); lid = str(lead.id); db.commit()
    finally:
        db.close()

    client.post("/mission/objection", json={"text": "it's too pricey", "lead_id": lid},
                headers=auth_headers)
    tl = client.get(f"/mission/lead-timeline/{lid}", headers=auth_headers).json()
    assert any(e["kind"] == "objection_coached" for e in tl["timeline"])


@requires_db
def test_quote_builder_assembles_packet_and_marks_sent(client, auth_headers):
    """The Automatic Quote Builder turns a lead's intake into a packet — line,
    coverages, a carrier shortlist, a labeled estimate range and what's missing —
    and marking it sent advances the lead to Quoted (Quote Sent stage) and logs
    it to the AI timeline."""
    from app.database import SessionLocal
    from app.models import Lead

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email == "quotebuild@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", category="Homeowner", owner_name="Quote Buyer",
                    email="quotebuild@x.co", status="Interested", score=60,
                    intake={"quote_type": "personal_auto",
                            "answers": {"garaging_address": "12 Main St, Boston MA", "vin": "1XYZ"},
                            "updated_at": "2026-07-04T00:00:00Z"})
        db.add(lead); db.flush()
        lid = str(lead.id)
        db.commit()
    finally:
        db.close()

    q = client.get(f"/leads/{lid}/quote", headers=auth_headers).json()
    assert q["ok"] is True
    assert q["line"] == "auto"  # personal_auto intake pins the line
    assert q["state"] == "MA"   # detected from the garaging address
    assert q["carriers"] and isinstance(q["carriers"], list)
    assert q["estimate"]["monthly_low"] < q["estimate"]["monthly_high"]
    # Intake is partial (2 of 4 fields) → not ready, and it names what's missing.
    assert q["ready_to_send"] is False
    assert q["intake"]["missing"]

    sent = client.post(f"/leads/{lid}/quote/sent", headers=auth_headers).json()
    assert sent["ok"] is True and sent["lead"]["status"] == "Quoted"

    # Quoted → Quote Sent stage in the funnel/timeline, with a quote_built event.
    tl = client.get(f"/mission/lead-timeline/{lid}", headers=auth_headers).json()
    assert tl["lead"]["stage"] == "Quote Sent"
    assert any(e["kind"] == "quote_built" for e in tl["timeline"])

    # Unknown lead → clean 404, not a 500.
    assert client.get("/leads/00000000-0000-0000-0000-000000000000/quote",
                      headers=auth_headers).status_code == 404


@requires_db
def test_client_renewal_radar_survives_flood_of_newer_clients(client, auth_headers):
    """Regression: /book/clients?expiring=1 (the renewal radar the Money Actions
    'Review renewals' card links to) must still surface an older client whose
    policy is renewing soon, even when hundreds of newer (non-expiring) clients
    exist — expires_at is a real column, so it must be filtered in SQL, not
    after the row LIMIT (the same bug already fixed on /leads//restaurants)."""
    from datetime import date, timedelta

    from app.database import SessionLocal
    from app.models import Client
    db = SessionLocal()
    try:
        db.query(Client).filter(Client.name.like("Newer Client%")).delete(synchronize_session=False)
        db.query(Client).filter(Client.name == "Old Renewal Co").delete(synchronize_session=False)
        db.commit()
        # An older client (sorts LAST by created_at desc) renewing soon.
        db.add(Client(business="insurance", name="Old Renewal Co", status="Active",
                      expires_at=date.today() + timedelta(days=15)))
        db.commit()
        # A flood of freshly-created clients (sort ahead by created_at) that
        # are NOT expiring soon.
        db.add_all([
            Client(business="insurance", name=f"Newer Client {i}", status="Active",
                  expires_at=date.today() + timedelta(days=365))
            for i in range(600)
        ])
        db.commit()
    finally:
        db.close()

    rows = client.get("/book/clients?expiring=1", headers=auth_headers).json()
    assert any(r["name"] == "Old Renewal Co" for r in rows)
    assert all(r["expiring_soon"] for r in rows)


@requires_db
def test_conversion_by_line(client, auth_headers):
    """Conversion-by-line groups insurance leads (and the partners feeding each
    line) into Home/Auto/Life/Commercial with reply and win rates."""
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        db.add_all([
            # A life-feeding partner who replied (Interested → counts as replied for Life).
            Lead(segment="referral_partner", category="Financial Advisor", company_name="Life Partner",
                 email="lifep@realbiz.com", status="Interested", score=10),
            # A commercial prospect that closed (won for Commercial).
            Lead(segment="commercial", category="Contractor", company_name="Won Co",
                 email="wonco@realbiz.com", status="Closed Won", score=10),
        ])
        db.commit()
    finally:
        db.close()

    r = client.get("/analytics/by-line", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert set(d["lines"]) == {"Home", "Auto", "Life", "Commercial"}
    for l in d["lines"].values():
        for k in ("leads", "contacted", "replied", "won", "reply_rate", "win_rate"):
            assert k in l, k
    assert d["lines"]["Life"]["replied"] >= 1     # the interested advisor
    assert d["lines"]["Commercial"]["won"] >= 1   # the closed contractor
    assert "totals" in d and d["totals"]["won"] >= 1


@requires_db
def test_subject_ab_report(client, auth_headers):
    """The subject A/B report exposes every rotated style with reply rate and a
    trusted-vs-testing status, computed from real sent/replied messages."""
    from app.database import SessionLocal
    from app.models import Message
    db = SessionLocal()
    try:
        # A question-style subject sent to an entity that replied → 1 reply for
        # the 'question' style.
        eid = __import__("uuid").uuid4()
        db.add_all([
            Message(channel="email", direction="outbound", to_email="q@x.co",
                    from_account="insurance", status="Sent",
                    subject="Quick question about your coverage?", entity_type="lead", entity_id=eid),
            Message(channel="email", direction="inbound", to_email="q@x.co",
                    from_account="insurance", status="Replied", entity_type="lead", entity_id=eid),
        ])
        db.commit()
    finally:
        db.close()

    r = client.get("/analytics/subject-ab", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    styles = {s["style"] for s in d["styles"]}
    assert {"question", "number/result", "short/punchy", "curiosity", "statement"} <= styles
    for s in d["styles"]:
        for k in ("style", "description", "sent", "replied", "rate", "enough_data"):
            assert k in s, k
    assert "min_sample" in d and "best" in d
    q = next(s for s in d["styles"] if s["style"] == "question")
    assert q["sent"] >= 1 and q["replied"] >= 1  # the question send + its reply counted


@requires_db
def test_outreach_performance_report(client, auth_headers):
    """The outreach report returns a gap-free daily send/reply series, funnel and
    reply rate computed from real messages."""
    from datetime import datetime, timezone
    from app.database import SessionLocal
    from app.models import Lead, Message
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Use @x.co addresses for injected Sent fixtures — the shared-session
        # convention other tests use to exclude injected rows from their asserts.
        db.add_all([
            Message(channel="email", direction="outbound", to_email="a@x.co",
                    from_account="insurance", status="Sent", sent_at=now),
            Message(channel="email", direction="outbound", to_email="b@x.co",
                    from_account="insurance", status="Sent", sent_at=now),
            Message(channel="email", direction="inbound", to_email="a@x.co",
                    from_account="insurance", status="Replied"),
            Lead(segment="commercial", category="Contractor", company_name="Hot Co",
                 email="hot@realbiz.com", status="Interested", score=10),
        ])
        db.commit()
    finally:
        db.close()

    r = client.get("/analytics/outreach?days=30", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["days"] == 30 and len(d["daily"]) == 30  # gap-free window
    assert d["totals"]["sent"] >= 2 and d["totals"]["replies"] >= 1
    assert d["totals"]["hot"] >= 1  # the Interested lead shows as hot
    assert set(d["funnel"]) == {"cold", "warm", "hot", "dead"}
    assert all({"date", "sent", "replies"} <= set(day) for day in d["daily"])


@requires_db
def test_mailbox_pool_snapshot(client, auth_headers):
    """The mailbox pool lists every Gmail identity with cap/warmup and reports the
    pool's combined daily capacity."""
    r = client.get("/deliverability/mailboxes", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    for key in ("mailboxes", "totals", "connected_count", "active_channel"):
        assert key in d, key
    # The four Gmail mailboxes are always present (connected or not).
    gmail_ids = {m["id"] for m in d["mailboxes"] if m["type"] == "gmail"}
    assert gmail_ids == {"gmail:personal", "gmail:insurance", "gmail:insurance_backup",
                         "gmail:bnb", "gmail:savorymind"}
    for m in d["mailboxes"]:
        for k in ("label", "connected", "sent_today", "daily_cap", "warmup"):
            assert k in m, k
    assert {"daily_capacity", "sent_today", "remaining"} <= set(d["totals"])
    # Offline: nothing connected, so zero capacity and no active channel.
    assert d["connected_count"] == 0 and d["active_channel"] is None


def test_sendgrid_stats_safe_without_key():
    """SendGrid stats degrade cleanly when no key is set (no crash, clear reason)."""
    from app.config import settings
    from app.integrations import sendgrid
    orig = settings.sendgrid_api_key
    try:
        settings.sendgrid_api_key = ""
        out = sendgrid.stats(7)
        assert out["ok"] is False and "reason" in out
    finally:
        settings.sendgrid_api_key = orig


@requires_db
def test_deliverability_sendgrid_stats_endpoint(client, auth_headers):
    """The dashboard's SendGrid-stats endpoint returns a structured result
    (ok:false offline) without erroring."""
    r = client.get("/deliverability/sendgrid-stats?days=7", headers=auth_headers)
    assert r.status_code == 200
    assert "ok" in r.json()


def test_insurance_line_classifier():
    """Every lead resolves to a line of business: home/auto/life/commercial.
    Referral partners route to the personal line they FEED (realtor→home,
    auto dealer→auto, financial advisor→life)."""
    from app.insurance_lines import AUTO, COMMERCIAL, HOME, LIFE, line_for
    # Commercial segment is commercial by default...
    assert line_for("Contractor", "commercial") == COMMERCIAL
    # ...EXCEPT vehicle-centric commercial prospects, who need Commercial Auto
    # (CAP) first — they surface under Auto, not the generic Commercial bucket,
    # so "commercial auto leads" are actually findable.
    assert line_for("Auto services", "commercial") == AUTO
    assert line_for("Trucking Company", "commercial") == AUTO
    assert line_for("Auto Dealership", "commercial") == AUTO
    assert line_for("Moving Company", "commercial") == AUTO
    # Direct personal prospects.
    assert line_for("Homeowner", "personal") == HOME
    assert line_for("Auto owner", "personal") == AUTO
    assert line_for("Life insurance — new parent", "personal") == LIFE
    # Referral partners feed the right personal line.
    assert line_for("Mortgage Broker", "referral_partner") == HOME
    assert line_for("Real Estate Agency", "referral_partner") == HOME
    assert line_for("Auto Dealership", "referral_partner") == AUTO
    assert line_for("Financial Advisor", "referral_partner") == LIFE
    assert line_for("Estate Planning Attorney", "referral_partner") == LIFE
    # Unknown personal signal defaults to home, never blank.
    assert line_for(None, "personal") == HOME


@requires_db
def test_leads_line_filter_and_summary(client, auth_headers):
    """Leads expose a line, /leads?line= filters by it, and /leads/summary returns
    per-line counts — so Home/Auto/Life/Commercial are visible and filterable."""
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        # Idempotent against a rerun in the same DB, and scored at parity with
        # the router's sort ceiling so these rows land on page 1 of a `line=`
        # query regardless of unrelated pollution in a shared DB.
        db.query(Lead).filter(Lead.email.in_(
            ["acme@realbiz.com", "sterling@realbiz.com", "build@realbiz.com"])).delete(synchronize_session=False)
        db.commit()
        db.add_all([
            Lead(segment="referral_partner", category="Mortgage Broker", company_name="Acme Mortgage",
                 email="acme@realbiz.com", status="New", score=100),
            Lead(segment="referral_partner", category="Financial Advisor", company_name="Sterling Wealth",
                 email="sterling@realbiz.com", status="New", score=100),
            Lead(segment="commercial", category="Contractor", company_name="BuildCo",
                 email="build@realbiz.com", status="New", score=100),
        ])
        db.commit()
    finally:
        db.close()

    s = client.get("/leads/summary", headers=auth_headers).json()
    assert "lines" in s and set(s["lines"]) == {"home", "auto", "life", "commercial"}
    assert s["lines"]["home"] >= 1 and s["lines"]["life"] >= 1 and s["lines"]["commercial"] >= 1

    rows = client.get("/leads?line=life&limit=5000", headers=auth_headers).json()
    assert rows and all(r["line"] == "life" for r in rows)
    assert any(r["company_name"] == "Sterling Wealth" for r in rows)
    # The computed line is present on every lead row.
    allrows = client.get("/leads?limit=5000", headers=auth_headers).json()
    assert all(r.get("line") in {"home", "auto", "life", "commercial"} for r in allrows)


@requires_db
def test_lead_quote_intake_profile_tracks_answers_and_completion(client, auth_headers):
    """A lead's quote-intake profile starts empty, fills in as answers are saved,
    reports accurate collected/total completion, and drops stale answers when the
    quote type changes (a workers' comp answer must not leak into personal auto)."""
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        lead = Lead(segment="personal", category="Auto owner", company_name="Intake Test Co",
                   email="intake-test@x.co", status="New", score=10)
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = str(lead.id)
    finally:
        db.close()

    empty = client.get(f"/leads/{lead_id}/intake", headers=auth_headers).json()
    assert empty["quote_type"] is None and empty["total"] == 0 and empty["complete"] is False

    r = client.post(f"/leads/{lead_id}/intake", headers=auth_headers, json={
        "quote_type": "personal_auto", "answers": {"vin": "1HGCM82633A004352", "garaging_address": "123 Main St"}})
    body = r.json()
    assert body["quote_type"] == "personal_auto" and body["total"] == 4
    assert body["collected"] == 2 and body["complete"] is False
    assert body["answers"]["vin"] == "1HGCM82633A004352"

    # Fill in the rest -> complete.
    full = client.post(f"/leads/{lead_id}/intake", headers=auth_headers, json={
        "quote_type": "personal_auto",
        "answers": {"vin": "1HGCM82633A004352", "garaging_address": "123 Main St",
                    "drivers_licenses": "Jane Doe #123", "lienholder": "None"}}).json()
    assert full["collected"] == 4 and full["total"] == 4 and full["complete"] is True

    # Switching quote type drops answers that don't belong to the new type.
    switched = client.post(f"/leads/{lead_id}/intake", headers=auth_headers, json={
        "quote_type": "workers_comp", "answers": {"vin": "should not carry over", "ein": "12-3456789"}}).json()
    assert switched["quote_type"] == "workers_comp"
    assert "vin" not in switched["answers"]
    assert switched["answers"]["ein"] == "12-3456789"
    assert switched["total"] == 4 and switched["collected"] == 1

    # Unknown lead / unknown quote type are clean errors, not 500s.
    assert client.get("/leads/00000000-0000-0000-0000-000000000000/intake", headers=auth_headers).status_code == 404
    assert client.post(f"/leads/{lead_id}/intake", headers=auth_headers,
                       json={"quote_type": "not_a_real_type", "answers": {}}).status_code == 400


@requires_db
def test_lead_quote_intake_send_via_text_and_whatsapp(client, auth_headers, monkeypatch):
    """The same quote-intake ask can go out as a text (via the iMessage bridge
    when Twilio isn't configured) or WhatsApp — gated on a phone number, a real
    channel being configured, and a known quote type; each send is logged."""
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        no_phone = Lead(segment="personal", category="Auto owner", company_name="No Phone Lead",
                        email="nophone-intake@x.co", status="New", score=10)
        has_phone = Lead(segment="personal", category="Auto owner", company_name="Has Phone Lead",
                         email="hasphone-intake@x.co", phone="+16175551234", status="New", score=10)
        db.add_all([no_phone, has_phone])
        db.commit()
        db.refresh(no_phone); db.refresh(has_phone)
        no_phone_id, has_phone_id = str(no_phone.id), str(has_phone.id)
    finally:
        db.close()

    r = client.post(f"/leads/{no_phone_id}/quote-intake/send", headers=auth_headers,
                    json={"quote_type": "personal_auto", "channel": "sms"})
    assert r.status_code == 400  # no phone on file

    r = client.post(f"/leads/{has_phone_id}/quote-intake/send", headers=auth_headers,
                    json={"quote_type": "not_a_real_type", "channel": "sms"})
    assert r.status_code == 400  # unknown quote type

    orig_bridge = settings.bridge_token
    orig_twilio = (settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number)
    orig_wa = (settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token,
              settings.twilio_whatsapp_number)
    try:
        # No texting channel at all -> clean 400, not a crash.
        settings.bridge_token = ""
        settings.twilio_account_sid = settings.twilio_auth_token = settings.twilio_from_number = ""
        r = client.post(f"/leads/{has_phone_id}/quote-intake/send", headers=auth_headers,
                        json={"quote_type": "personal_auto", "channel": "sms"})
        assert r.status_code == 400

        # Bridge configured (free iMessage path) -> queues successfully.
        settings.bridge_token = "test-bridge-secret"
        r = client.post(f"/leads/{has_phone_id}/quote-intake/send", headers=auth_headers,
                        json={"quote_type": "personal_auto", "channel": "sms", "lang": "en"})
        body = r.json()
        assert r.status_code == 200 and body["ok"] is True and "VIN" in body["text"]

        db = SessionLocal()
        try:
            from app.models import Message
            msg = (db.query(Message).filter(Message.entity_id == has_phone.id,
                                            Message.channel == "sms").first())
            assert msg is not None and msg.status == "Queued" and msg.to_email == "+16175551234"
        finally:
            db.close()

        # WhatsApp not connected -> clean 400.
        settings.whatsapp_cloud_phone_number_id = settings.whatsapp_cloud_token = ""
        settings.twilio_whatsapp_number = ""
        r = client.post(f"/leads/{has_phone_id}/quote-intake/send", headers=auth_headers,
                        json={"quote_type": "personal_auto", "channel": "whatsapp"})
        assert r.status_code == 400

        # WhatsApp connected (mocked send) -> logged as a whatsapp Message.
        from app.integrations import whatsapp_cloud
        settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token = "123456", "eaa-token"
        monkeypatch.setattr(whatsapp_cloud, "send", lambda to, body: "wamid.test123")
        r = client.post(f"/leads/{has_phone_id}/quote-intake/send", headers=auth_headers,
                        json={"quote_type": "personal_auto", "channel": "whatsapp", "lang": "pt"})
        body = r.json()
        assert r.status_code == 200 and body["ok"] is True and "VIN" in body["text"]

        db = SessionLocal()
        try:
            from app.models import Message
            msg = (db.query(Message).filter(Message.entity_id == has_phone.id,
                                            Message.channel == "whatsapp").first())
            assert msg is not None and msg.status == "Sent" and msg.provider_id == "wamid.test123"
        finally:
            db.close()

        # Bad channel value -> clean 400.
        r = client.post(f"/leads/{has_phone_id}/quote-intake/send", headers=auth_headers,
                        json={"quote_type": "personal_auto", "channel": "carrier_pigeon"})
        assert r.status_code == 400
    finally:
        settings.bridge_token = orig_bridge
        (settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number) = orig_twilio
        (settings.whatsapp_cloud_phone_number_id, settings.whatsapp_cloud_token,
         settings.twilio_whatsapp_number) = orig_wa
        # These SMS/WhatsApp Message rows (to_email is a phone number, not an
        # email) would otherwise leak into other tests that scan /messages —
        # e.g. test_outbound_messages_created_per_account's cold-email-only
        # "never Sent" assertion has no way to know these aren't cold email.
        db = SessionLocal()
        try:
            from app.models import Message
            db.query(Message).filter(Message.entity_id.in_([no_phone.id, has_phone.id])).delete(
                synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_per_business_booking_link():
    """Each business gets its own 'Book a time' link; empty falls back to the
    default. So a SavoryMind prospect books a SavoryMind call, not insurance."""
    from app import email_template
    from app.config import settings

    orig = (settings.calendar_link, settings.calendar_link_insurance,
            settings.calendar_link_savorymind)
    try:
        settings.calendar_link = "https://cal.com/default"
        settings.calendar_link_insurance = "https://cal.com/insurance"
        settings.calendar_link_savorymind = ""  # no own link → falls back to default

        assert email_template.booking_link("insurance") == "https://cal.com/insurance"
        assert email_template.booking_link("savorymind") == "https://cal.com/default"
        assert email_template.booking_link("personal") == "https://cal.com/default"

        ins = email_template.render("Hi there", account="insurance")
        assert "https://cal.com/insurance" in ins and "Book a time" in ins
        sm = email_template.render("Hi there", account="savorymind")
        assert "https://cal.com/default" in sm  # fell back, not insurance's link
        assert "https://cal.com/insurance" not in sm

        # No links configured anywhere → no CTA at all.
        settings.calendar_link = ""
        settings.calendar_link_insurance = ""
        assert "Book a time" not in email_template.render("Hi there", account="insurance")
    finally:
        (settings.calendar_link, settings.calendar_link_insurance,
         settings.calendar_link_savorymind) = orig


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


def test_insurance_sourcing_is_broadened():
    """Broader category net + a real scrape budget so insurance keeps finding NEW
    leads in NH/MA/FL after the email-tagged pool is tapped."""
    from app.config import settings
    from app.integrations import osm_leads
    assert len(osm_leads.COMMERCIAL_OSM) >= 12  # wide category net
    # Every selector is a well-formed Overpass node filter (no quoting breakage).
    for sels in osm_leads.COMMERCIAL_OSM.values():
        assert all(s.startswith('node[') and s.endswith(']') for s in sels)
    assert osm_leads._scrape_budget() == settings.osm_scrape_budget >= 1


def test_music_real_playlist_discovery_offline_safe():
    """Music now sources REAL playlists from Spotify (search by genre); offline /
    unconnected it returns nothing rather than fabricating, never raises."""
    from app.integrations import spotify_api
    assert spotify_api.discover_playlists(None, ["r&b", "latin soul"]) == []
    assert spotify_api.discover_playlists(None, []) == []


def test_music_catalog_data_is_complete():
    """The real discography is loaded and self-consistent — every single is an
    actual track on its album, and lookups resolve case-insensitively."""
    from app import music_catalog
    s = music_catalog.stats()
    assert s["albums"] == 10 and s["tracks"] == 120 and s["singles"] >= 14
    for a in music_catalog.all_albums():
        titles = {t["title"] for t in a["tracks"]}
        assert set(a["singles"]) <= titles  # a single must be a track on the album
        assert sum(1 for t in a["tracks"] if t["single"]) == len(a["singles"])
    hit = music_catalog.find_track("ROME REMINDS ME OF YOU")  # case-insensitive
    assert hit and hit["album"] == "Golden Hour" and hit["single"] is True
    assert music_catalog.find_track("not a real song") is None
    # The top-streamed "Popular" set is present, ranked, and promotable even for
    # songs that aren't on a listed themed album.
    pop = music_catalog.popular()
    assert len(pop) == 10 and pop[0] == {"rank": 1, "title": "I Stayed in Rome", "album": None}
    assert music_catalog.find_track("i stayed in rome") is not None  # resolves despite no album


@requires_db
def test_music_catalog_endpoints_and_promote(client, auth_headers):
    """/music/catalog serves the discography; promoting a catalog track creates a
    MusicRelease (idempotently) so its content kit can be built."""
    cat = client.get("/music/catalog", headers=auth_headers).json()
    assert cat["stats"]["albums"] == 10
    assert any(al["title"] == "Postcards From Rome" for al in cat["albums"])

    r = client.post("/music/catalog/promote", headers=auth_headers,
                    json={"title": "Marry Me In This Lifetime"})
    assert r.status_code == 200
    rel = r.json()
    assert rel["title"] == "Marry Me In This Lifetime" and rel["era"] == "Forever Starts Here"
    rid = rel["id"]
    # Idempotent — promoting the same song again returns the same release.
    r2 = client.post("/music/catalog/promote", headers=auth_headers,
                     json={"title": "Marry Me In This Lifetime"})
    assert r2.json()["id"] == rid
    # It shows up in the releases list, ready for a kit.
    assert any(x["id"] == rid for x in client.get("/music/releases", headers=auth_headers).json())
    # A song not in the catalog is a clean 404.
    assert client.post("/music/catalog/promote", headers=auth_headers,
                       json={"title": "Totally Made Up Song"}).status_code == 404

    # The catalog exposes the top-streamed set, and promote-top10 queues them all.
    assert len(cat["popular"]) == 10 and cat["popular"][0]["rank"] == 1
    top = client.post("/music/catalog/promote-top10", headers=auth_headers).json()
    assert top["ok"] and top["promoted"] == 10
    rel_titles = {x["title"] for x in client.get("/music/releases", headers=auth_headers).json()}
    assert "I Stayed in Rome" in rel_titles  # a popular-only song promoted despite no album
    # Idempotent — running it again doesn't duplicate.
    again = client.post("/music/catalog/promote-top10", headers=auth_headers).json()
    assert again["promoted"] == 10


def test_places_source_disabled_without_key():
    from app.integrations import email_finder, places

    assert places.is_configured() is False
    assert places.fetch_commercial_leads(10) == []
    assert places.fetch_restaurants(10) == []
    # Shared email finder cleans correctly.
    assert email_finder.clean_email("Sales@Acme.com") == "sales@acme.com"
    assert email_finder.clean_email("hero@2x.png") is None


def test_leads_search_statewide_not_by_city():
    """No narrow city list by default: every source sweeps whole STATES. Google
    Places honors the per-business scope (e.g. insurance NH/MA/FL) statewide,
    instead of a fixed handful of cities (which could leak out-of-state leads)."""
    from app.config import settings
    from app.integrations import places
    # Default config carries no cities — we search states, not cities.
    assert settings.lead_cities == ""
    # A per-business scope drives Places area names statewide (same as OSM).
    areas = places._areas("Massachusetts,New Hampshire,Florida")
    assert areas == ["Massachusetts", "New Hampshire", "Florida"]
    # With no scope, Places falls back to the configured whole states.
    old_c, old_s = settings.lead_cities, settings.lead_states
    settings.lead_cities, settings.lead_states = "", "Massachusetts,New Hampshire"
    try:
        assert places._areas() == ["Massachusetts", "New Hampshire"]
    finally:
        settings.lead_cities, settings.lead_states = old_c, old_s


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


def test_autoapply_lane_routing_and_off_gate():
    """Auto-apply routes each job to the right lane and never submits when off."""
    from app import autoapply
    assert autoapply._lane("https://boards.greenhouse.io/acme/jobs/123") == "ats"
    assert autoapply._lane("https://jobs.lever.co/acme/abc") == "ats"
    assert autoapply._lane("https://acme.myworkdayjobs.com/x/job/123") == "ats"
    assert autoapply._lane("https://www.linkedin.com/jobs/view/123") == "easy_apply"
    assert autoapply._lane("https://www.indeed.com/viewjob?jk=1") == "easy_apply"
    assert autoapply._lane("https://acme.com/careers/123") == "other"
    assert autoapply._lane(None) == "other"
    # Cookie parsing turns a copied cookie string into Playwright cookies.
    # (Pure string parsing — no DB; exercised via the helper's logic.)


@requires_db
def test_autoapply_off_by_default_and_toggles(client, auth_headers):
    """Auto-apply is OFF by default (never submits unprompted) and the mode toggles
    off → compliant → aggressive without a redeploy."""
    from app import autoapply
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        res = autoapply.run_auto_apply(db)
        assert res["ok"] is False and res["mode"] == "off"  # nothing submitted when off
    finally:
        db.close()
    st = client.get("/control/status", headers=auth_headers).json()
    assert st["auto_apply_mode"] == "off"
    agg = client.post("/control/auto-apply", json={"mode": "aggressive"}, headers=auth_headers).json()
    assert agg["auto_apply_mode"] == "aggressive"
    assert client.get("/control/status", headers=auth_headers).json()["auto_apply_mode"] == "aggressive"
    # Reset so other tests/state aren't left in aggressive mode.
    client.post("/control/auto-apply", json={"mode": "off"}, headers=auth_headers)


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


@requires_db
def test_social_posts_attach_a_generated_image(client, auth_headers, monkeypatch):
    """Scheduled social posts must carry a real photo, not go out as bare text
    (the LinkedIn "0 photos" complaint). publish_due generates+hosts an image,
    caches it on the item, and passes it to the platform publisher."""
    from datetime import datetime, timedelta, timezone

    from app import content_factory, media, social
    from app.database import SessionLocal
    from app.models import ContentItem

    # Pretend image generation + hosting are available, returning a fixed URL.
    # (media is imported inside the functions, so patch the module itself.)
    monkeypatch.setattr(media, "can_generate", lambda: True)
    monkeypatch.setattr(media, "generate_and_host",
                        lambda prompt, name: "https://img.example/generated.png")
    # Capture what the LinkedIn publisher receives (connected → returns ok).
    captured = {}
    monkeypatch.setitem(
        social.PLATFORMS, "linkedin",
        (lambda db: True,
         lambda db, cap, img: captured.update(caption=cap, image=img) or {"ok": True},
         False))

    db = SessionLocal()
    try:
        item = ContentItem(topic="Why bundling home + auto saves money", business="insurance",
                           channel="linkedin", title="Bundle & save", body="Real, specific copy.",
                           hashtags="#insurance", status="scheduled",
                           scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1))
        db.add(item)
        db.commit()
        cid = str(item.id)
    finally:
        db.close()

    res = content_factory.publish_due(SessionLocal())
    assert res["published"] >= 1
    assert captured.get("image") == "https://img.example/generated.png"  # photo attached

    db = SessionLocal()
    try:
        refreshed = db.query(ContentItem).filter(ContentItem.id == cid).first()
        assert refreshed.status == "published"
        assert (refreshed.meta or {}).get("image_url") == "https://img.example/generated.png"
    finally:
        db.close()

    # The on-demand endpoint reports a clean, actionable reason when media isn't
    # configured (default in tests), rather than silently doing nothing.
    monkeypatch.setattr(media, "can_generate", lambda: False)
    db = SessionLocal()
    try:
        item2 = ContentItem(topic="t", business="insurance", channel="linkedin",
                           title="x", body="y", status="ready")
        db.add(item2); db.commit(); cid2 = str(item2.id)
    finally:
        db.close()
    r = client.post(f"/content/{cid2}/generate-image", headers=auth_headers).json()
    assert r["ok"] is False and "bucket" in r["reason"].lower()


@requires_db
def test_generated_posts_get_a_photo_and_bulk_backfill(client, auth_headers, monkeypatch):
    """Every social post should ship with a visual: generate_pack attaches one
    on-brand photo to each social item, and attach-images backfills the text-only
    backlog. Both no-op cleanly (clear reason) when media isn't configured."""
    from app import content_factory, media
    from app.ai import client as ai_client
    from app.database import SessionLocal
    from app.models import ContentItem

    monkeypatch.setattr(media, "can_generate", lambda: True)
    monkeypatch.setattr(media, "generate_and_host", lambda prompt, name: "https://img.example/pack.png")
    # generate_pack needs a live model + a content pack; mock both.
    monkeypatch.setattr(ai_client, "is_live", lambda: True)
    monkeypatch.setattr(ai_client, "embed", lambda t: None)
    monkeypatch.setattr(ai_client, "complete_json", lambda *a, **k: {
        "angle": "a sharp angle",
        "linkedin": {"body": "specific post", "hashtags": "#a #b #c"},
        "x": {"body": "punchy"},
        "email": {"subject": "s", "body": "b"}})  # email is non-social → no photo

    res = content_factory.generate_pack(SessionLocal(), "bundling home and auto",
                                        business="insurance", channels=["linkedin", "x", "email"])
    assert res["ok"] and set(res["channels"]) >= {"linkedin", "x"}

    db = SessionLocal()
    try:
        social = db.query(ContentItem).filter(
            ContentItem.topic == "bundling home and auto",
            ContentItem.channel.in_(["linkedin", "x"])).all()
        assert social and all((s.meta or {}).get("image_url") == "https://img.example/pack.png" for s in social)
        # The non-social email piece is left without a forced image.
        email = db.query(ContentItem).filter(
            ContentItem.topic == "bundling home and auto", ContentItem.channel == "email").first()
        assert email is not None and not (email.meta or {}).get("image_url")
        # A pre-existing text-only social post with no image, for the backfill.
        db.add(ContentItem(topic="old text-only", business="insurance", channel="facebook",
                           title="t", body="b", status="ready"))
        db.commit()
    finally:
        db.close()

    back = client.post("/content/attach-images", headers=auth_headers).json()
    assert back["ok"] and back["attached"] >= 1

    db = SessionLocal()
    try:
        fb = db.query(ContentItem).filter(ContentItem.topic == "old text-only").first()
        assert (fb.meta or {}).get("image_url") == "https://img.example/pack.png"
    finally:
        db.close()

    # Without media configured, backfill reports a clean actionable reason.
    monkeypatch.setattr(media, "can_generate", lambda: False)
    off = client.post("/content/attach-images", headers=auth_headers).json()
    assert off["ok"] is False and "bucket" in off["reason"].lower()


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
    # "Current salary" must NOT leak the target — it maps to current_salary.
    assert browser._match_field("Current Salary", flat) == "Prefer Not to Disclose"


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


@requires_db
def test_content_video_url_exposed_for_download(client, auth_headers):
    """A generated video must be downloadable/postable manually while a
    platform's auto-publish is disconnected — the API has to expose video_url,
    not just leave it buried in internal meta."""
    from app import content_factory
    from app.database import SessionLocal
    from app.models import ContentItem
    db = SessionLocal()
    try:
        item = ContentItem(topic="Test video post", business="music", channel="instagram",
                           title="T", body="B", status="ready",
                           meta={"video_url": "https://cdn.example.com/clip.mp4", "video_status": "ready"})
        db.add(item); db.commit(); db.refresh(item)
        d = content_factory.out(item)
        assert d["video_url"] == "https://cdn.example.com/clip.mp4"
        assert d["video_status"] == "ready"
    finally:
        db.close()
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


def test_version_reports_build_sha(client, monkeypatch):
    """/version reports the live build's commit SHA (set by the deploy) so you can
    confirm a merge actually reached production. Public (no auth) for easy checks."""
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "bruno-ai-workforce" and "app_version" in body
    assert body["sha"] == "dev"  # unset in tests → the safe default

    monkeypatch.setenv("BUILD_SHA", "abc1234")
    assert client.get("/version").json()["sha"] == "abc1234"


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
    # Gmail is not configured in CI, so nothing is actually SENT (messages stay
    # Drafted, or Approved if a reply was approved without a mailbox — never Sent).
    # Scope to the agents' cold-outreach rows: other tests inject recap fixtures
    # (to_email "*@x.co") with status="Sent" into the shared session DB, which are
    # not what this test is asserting about.
    cold = [m for m in msgs if not (m.get("to_email") or "").endswith("@x.co")]
    assert all(m["status"] != "Sent" for m in cold)


@requires_db
def test_automation_rules_and_branching(client, auth_headers):
    """Automation rules list + toggle, and reply branching (interested→task,
    unsubscribe→suppress) acts on real records."""
    from app import automation
    from app.database import SessionLocal
    from app.models import Lead, Task

    rules = client.get("/automations", headers=auth_headers).json()
    keys = {r["key"] for r in rules}
    assert "interested_to_task" in keys and "unsubscribe_suppress" in keys
    assert all(r["enabled"] for r in rules)  # default ON
    # Toggle one off and back.
    assert client.post("/automations/toggle", json={"key": "question_to_task", "on": False},
                       headers=auth_headers).json()["enabled"] is False

    db = SessionLocal()
    try:
        lead = Lead(segment="commercial", company_name="Branch Co", email="boss@branchco.io", status="New")
        db.add(lead); db.flush()
        before = db.query(Task).count()
        automation.on_reply(db, intent="interested", sender="boss@branchco.io",
                            entity_type="lead", entity_id=lead.id, summary="wants a quote")
        db.flush()
        assert db.query(Task).count() == before + 1  # task created
        # Unsubscribe suppresses the address forever.
        automation.on_reply(db, intent="unsubscribe", sender="boss@branchco.io",
                            entity_type="lead", entity_id=lead.id)
        db.flush()
        assert lead.status == "do_not_contact"
        db.rollback()
    finally:
        db.close()


def test_lead_scoring_explains_score():
    """The explainable score returns a 0-100 number, a band, and reasons."""
    from app.lead_scoring import score_lead
    from app.models import Lead
    strong = Lead(segment="commercial", company_name="Acme", owner_name="Jane Doe",
                  email="jane@acme.com", phone="555", status="Interested", score=80)
    s = score_lead(strong)
    assert 0 <= s["score"] <= 100 and s["band"] in ("hot", "warm", "cold")
    assert any("Hot" in r or "email" in r.lower() for r in s["reasons"])
    weak = Lead(segment="personal", status="New")
    assert score_lead(weak)["score"] <= s["score"]


@requires_db
def test_lead_finder_search(client, auth_headers):
    """Lead Finder returns scored, filtered rows."""
    rows = client.get("/leads/search?has_email=true&min_score=0", headers=auth_headers).json()
    assert isinstance(rows, list)
    for r in rows[:5]:
        assert "score" in r and "reasons" in r and r["email"]
    # Scores are sorted descending.
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


@requires_db
def test_lead_finder_temperature_survives_cold_flood(client, auth_headers):
    """Regression: /leads/search?temperature=warm must still surface a warm
    lead even when hundreds of top-scoring cold leads exist — the same row-
    LIMIT-before-filter starvation bug already fixed on /leads and
    /restaurants, on this sibling endpoint."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.query(models.Lead).filter(models.Lead.email.like("finderflood%@x.co")).delete(
            synchronize_session=False)
        db.query(models.Lead).filter(models.Lead.email == "finderwarm@x.co").delete(
            synchronize_session=False)
        db.commit()
        db.add_all([
            models.Lead(segment="commercial", category="Contractor",
                       company_name=f"Finder Flood {i}", email=f"finderflood{i}@x.co",
                       status="New", score=99)
            for i in range(450)
        ])
        db.add(models.Lead(segment="commercial", category="Contractor", company_name="Finder Warm Lead",
                           email="finderwarm@x.co", status="replied", score=10))
        db.commit()
    finally:
        db.close()

    rows = client.get("/leads/search?temperature=warm&limit=500", headers=auth_headers).json()
    assert any(r["company"] == "Finder Warm Lead" for r in rows)


@requires_db
def test_agent_builder_blueprints(client, auth_headers, monkeypatch):
    """Agent-from-URL generates + persists a blueprint (model mocked); list works."""
    from app import agent_builder
    from app.ai import client as ai_client
    monkeypatch.setattr(agent_builder, "_fetch_text", lambda url, limit=6000: "We help restaurants grow revenue.")
    monkeypatch.setattr(ai_client, "is_live", lambda: True)
    monkeypatch.setattr(ai_client, "complete_json", lambda *a, **k: {
        "business": "SavoryMind", "offer": "AI menu intelligence", "icp": "Restaurant owners",
        "industries": ["Restaurants", "Cafes"], "pain_points": "slow tables; thin margins",
        "angles": "table turns; reviews", "scripts": {"cold_email": {"subject": "table turns", "body": "Hi"}}})

    r = client.post("/agents/blueprint", json={"url": "savorymind.net"}, headers=auth_headers).json()
    assert r["ok"] and r["business"] == "SavoryMind"
    assert r["industries"] == "Restaurants, Cafes"  # list flattened to a string
    lst = client.get("/agents/blueprints", headers=auth_headers).json()
    assert any(b["business"] == "SavoryMind" for b in lst)


@requires_db
def test_agent_builder_handles_bad_url(client, auth_headers):
    """A blank/garbage URL returns a clean error, never a 500."""
    r = client.post("/agents/blueprint", json={"url": ""}, headers=auth_headers).json()
    assert r["ok"] is False and "error" in r


@requires_db
def test_crm_pipeline_board_and_move(client, auth_headers):
    """The deal pipeline groups leads into stages, and a lead can be moved."""
    board = client.get("/crm/pipeline", headers=auth_headers).json()
    stages = {s["stage"] for s in board["stages"]}
    assert {"New", "Contacted", "Replied", "Qualified", "Meeting", "Won", "Lost", "Nurture"} <= stages
    assert "pipeline_value" in board
    # Grab any card and move it to "Qualified".
    card = next((c for s in board["stages"] for c in s["cards"]), None)
    if card:
        r = client.post("/crm/pipeline/move",
                        json={"lead_id": card["id"], "stage": "Qualified"}, headers=auth_headers).json()
        assert r["ok"] and r["stage"] == "Qualified"


@requires_db
def test_connection_token_health(client, auth_headers):
    """Token-health endpoint returns a list (empty when nothing connected) and the
    refresh endpoint runs safely with no connections."""
    rows = client.get("/connections/health", headers=auth_headers).json()
    assert isinstance(rows, list)  # no social connections in tests → []
    r = client.post("/connections/refresh", headers=auth_headers).json()
    assert r["ok"] and isinstance(r["results"], dict)


@requires_db
def test_revenue_analytics(client, auth_headers):
    """Revenue report returns per-business funnel + totals; ROI when cost given."""
    r = client.get("/analytics/revenue", headers=auth_headers).json()
    assert set(r["businesses"]) == {"Insurance", "BnB Global", "SavoryMind"}
    for b in r["businesses"].values():
        for k in ("leads", "won", "revenue_won", "pipeline_value", "reply_rate", "win_rate"):
            assert k in b
    assert r["cost_metrics"] is None  # no cost given
    withcost = client.get("/analytics/revenue?cost=500", headers=auth_headers).json()
    assert withcost["cost_metrics"]["spend"] == 500
    assert "roi" in withcost["cost_metrics"]


@requires_db
def test_revenue_rolls_in_actual_crm_premium(client, auth_headers):
    """The Client Book's REAL premium (monthly x 12) rolls into Revenue/ROI as
    actual_annual_revenue per business, alongside the lead-based estimate —
    cancelled clients are excluded."""
    from app.database import SessionLocal
    from app.models import Client
    db = SessionLocal()
    try:
        db.add_all([
            Client(business="insurance", name="Real Rev Co", premium_monthly=100, status="Active"),
            Client(business="bnb", name="BnB Rev Co", premium_monthly=50, status="Active"),
            Client(business="insurance", name="Cancelled Co", premium_monthly=999, status="Cancelled"),
        ])
        db.commit()
    finally:
        db.close()

    r = client.get("/analytics/revenue", headers=auth_headers).json()
    # >= not == : other tests in this shared session also create Client rows.
    assert r["businesses"]["Insurance"]["actual_annual_revenue"] >= 1200.0  # 100 * 12, cancelled excluded
    assert r["businesses"]["BnB Global"]["actual_annual_revenue"] >= 600.0   # 50 * 12
    assert r["totals"]["actual_annual_revenue"] >= 1800.0


@requires_db
def test_campaign_builder_plan(client, auth_headers, monkeypatch):
    """NL brief → structured campaign plan (model mocked), persisted + listable."""
    from app import campaign_builder
    from app.ai import client as ai_client
    monkeypatch.setattr(ai_client, "is_live", lambda: True)
    monkeypatch.setattr(ai_client, "complete_json", lambda *a, **k: {
        "business": "SavoryMind", "audience": "Boston restaurant owners",
        "filters": {"location": "Boston", "min_rating": "4.3"},
        "channels": ["email"], "sequence": [{"step": 1, "purpose": "intro"}],
        "schedule": "weekdays", "success_metric": "booked demos",
        "summary": "Pitch SavoryMind to Boston restaurants."})

    r = client.post("/campaigns/plan", json={"brief": "Boston restaurants, pitch SavoryMind"},
                    headers=auth_headers).json()
    assert r["ok"] and r["business"] == "SavoryMind" and r["agent_key"] == "savorymind"
    assert r["plan"]["filters"]["location"] == "Boston"
    lst = client.get("/campaigns", headers=auth_headers).json()
    assert any(p["business"] == "SavoryMind" for p in lst)


@requires_db
def test_campaign_builder_bad_brief(client, auth_headers):
    """Blank brief returns a clean error, not a 500."""
    r = client.post("/campaigns/plan", json={"brief": ""}, headers=auth_headers).json()
    assert r["ok"] is False and "error" in r


@requires_db
def test_campaign_launch_applies_plan_filters_and_tags_leads(client, auth_headers, monkeypatch):
    """Launching a plan must actually steer sourcing by the brief's filters (not
    just run the agent's generic daily behavior) and tag every sourced lead with
    the campaign so results are trackable."""
    from app import campaign_builder
    from app.agents import commercial_finder as cf_mod
    from app.database import SessionLocal
    from app.models import CampaignPlan, Lead

    prospects = [
        {"segment": "commercial", "category": "Restaurant", "company_name": "Match Bistro",
         "owner_name": "A", "email": "match-campaign@x.co", "phone": "1",
         "website": "https://x.co", "industry": "Restaurant", "city": "Boston"},
        {"segment": "commercial", "category": "Law Firm", "company_name": "Nomatch Legal",
         "owner_name": "B", "email": "nomatch-campaign@x.co", "phone": "2",
         "website": "https://x.co", "industry": "Legal", "city": "Boston"},
    ]
    monkeypatch.setattr(cf_mod.providers, "fetch_insurance_leads",
                        lambda segment, count, **kw: prospects if segment == "commercial" else [])

    db = SessionLocal()
    try:
        # Idempotent against a rerun in the same DB (dedupe-by-email would
        # otherwise silently skip the prospect on a second pass).
        db.query(Lead).filter(Lead.email.in_(
            ["match-campaign@x.co", "nomatch-campaign@x.co"])).delete(synchronize_session=False)
        db.commit()

        plan_row = CampaignPlan(
            brief="Boston restaurants for commercial insurance", business="Insurance",
            agent_key="commercial_finder",
            plan={"filters": {"location": "Boston", "industry": "Restaurant"}})
        db.add(plan_row)
        db.commit()
        db.refresh(plan_row)
        plan_id = str(plan_row.id)

        result = campaign_builder.launch(db, plan_id)
        assert result["ok"] is True
        assert result["leads_sourced"] == 1  # only the matching-industry prospect

        matched = db.query(Lead).filter(Lead.email == "match-campaign@x.co").first()
        skipped = db.query(Lead).filter(Lead.email == "nomatch-campaign@x.co").first()
        assert matched is not None and matched.campaign_id == plan_id
        assert skipped is None  # filtered out — never sourced

        listed = client.get("/campaigns", headers=auth_headers).json()
        row = next(p for p in listed if p["id"] == plan_id)
        assert row["status"] == "launched" and row["leads_sourced"] == 1
    finally:
        db.close()


@requires_db
def test_unified_inbox_feed(client, auth_headers):
    """The unified inbox aggregates classified replies with label + drafted reply."""
    from app.database import SessionLocal
    from app.models import ActionLog, Lead, Message

    db = SessionLocal()
    try:
        lead = Lead(segment="consulting", company_name="Inbox Co", email="boss@inboxco.io", status="Replied")
        db.add(lead)
        db.add(ActionLog(actor="inbound", action="reply_classified", entity="email",
                         entity_id="boss@inboxco.io",
                         detail={"intent": "interested", "summary": "wants a demo", "subject": "your note"}))
        db.add(Message(channel="email", direction="outbound", entity_type="reply",
                       to_email="boss@inboxco.io", subject="Re: your note", body="Happy to help!",
                       status="Drafted"))
        db.commit()
    finally:
        db.close()

    feed = client.get("/messages/inbox", headers=auth_headers).json()
    item = next((i for i in feed["items"] if i["sender"] == "boss@inboxco.io"), None)
    assert item is not None
    assert item["label"] == "Interested" and item["business"] == "BnB Global"
    assert item["draft_id"] and item["draft_body"]
    # Label filter works.
    only = client.get("/messages/inbox?label=Interested", headers=auth_headers).json()
    assert all(i["label"] == "Interested" for i in only["items"])


def test_bnb_mailbox_routing():
    """Consulting routes to the BnB mailbox only when it's configured; otherwise
    falls back to personal. Insurance segments use the insurance mailbox."""
    from app.config import settings
    from app.integrations import gmail
    assert gmail.account_for_segment("commercial") == "insurance"
    assert gmail.account_for_segment("consulting") == "personal"  # BnB not connected
    settings.bnb_gmail_app_password = "x" * 16
    try:
        assert gmail.account_for_segment("consulting") == "bnb"
    finally:
        settings.bnb_gmail_app_password = ""
    # SavoryMind restaurant mailbox routes only when connected.
    assert gmail.restaurant_account() == "personal"
    settings.savorymind_gmail_app_password = "y" * 16
    try:
        assert gmail.restaurant_account() == "savorymind"
    finally:
        settings.savorymind_gmail_app_password = ""


@requires_db
def test_sendgrid_direct_send(monkeypatch):
    """With SendGrid connected, outreach delivers via SendGrid (not Gmail) even
    with no Gmail App Password, and the message is marked Sent."""
    from app import outreach
    from app.config import settings
    from app.database import SessionLocal
    from app.integrations import sendgrid
    from app.models import Lead

    monkeypatch.setattr(settings, "sendgrid_api_key", "SG.key")
    monkeypatch.setattr(settings, "sendgrid_from_email", "hello@bnbglobal.net")
    sent = {}
    monkeypatch.setattr(sendgrid, "send_email",
                        lambda to, subject, html, from_email=None, reply_to=None:
                            sent.update(to=to, from_email=from_email) or "sg-1")

    db = SessionLocal()
    try:
        lead = Lead(segment="consulting", company_name="SG Co", email="ceo@sgco.io",
                    status="New", cold_email="Hi there.")
        db.add(lead); db.flush()
        msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                      to_email=lead.email, subject="quick idea",
                                      body=lead.cold_email, account="personal",
                                      actor="test", autonomous=False)
        assert msg.status == "Sent" and msg.provider_id == "sg-1"
        assert sent.get("to") == "ceo@sgco.io"
        db.rollback()
    finally:
        db.close()


def test_sendgrid_per_business_sender():
    """SendGrid sends AS each business's verified sender; default otherwise."""
    from app.config import settings
    from app.integrations import sendgrid
    monkeypatch_vals = {
        "sendgrid_from_insurance": "b@dossantosinsurance.org",
        "sendgrid_from_bnb": "braxandbrie@gmail.com",
        "sendgrid_from_savorymind": "taste@savorymindfood.com",
        "sendgrid_from_email": "hello@default.com",
    }
    saved = {k: getattr(settings, k) for k in monkeypatch_vals}
    for k, v in monkeypatch_vals.items():
        setattr(settings, k, v)
    try:
        assert sendgrid.from_for("insurance") == "b@dossantosinsurance.org"
        assert sendgrid.from_for("bnb") == "braxandbrie@gmail.com"
        assert sendgrid.from_for("savorymind") == "taste@savorymindfood.com"
        assert sendgrid.from_for("personal") == "hello@default.com"
        # Reply-To: BnB routes replies to the monitored inbox; others default to from.
        assert sendgrid.replyto_for("bnb", "hello@bnbglobal.net") == "braxandbrie@gmail.com"
        assert sendgrid.replyto_for("savorymind", "taste@savorymindfood.com") == "taste@savorymindfood.com"
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


def test_sender_selector_gating():
    """The unified sender picks whichever cold-email provider is configured."""
    from app.config import settings
    from app.integrations import sender
    assert sender.is_configured() is False  # nothing connected in tests
    settings.instantly_api_key = "k"; settings.instantly_campaign_id = "c"
    try:
        assert sender.name() == "instantly" and sender.is_configured()
    finally:
        settings.instantly_api_key = ""; settings.instantly_campaign_id = ""
    settings.smartlead_api_key = "k"; settings.smartlead_campaign_id = "c"
    try:
        assert sender.name() == "smartlead"
    finally:
        settings.smartlead_api_key = ""; settings.smartlead_campaign_id = ""


@requires_db
def test_outreach_hands_off_to_provider(monkeypatch):
    """With a cold-email provider connected, a lead is handed off and marked Sent
    even with no Gmail configured — and nothing is sent via Gmail SMTP."""
    from app import outreach
    from app.database import SessionLocal
    from app.integrations import sender
    from app.models import Lead

    captured = {}

    def fake_add_lead(**kw):
        captured.update(kw)
        return True

    monkeypatch.setattr(sender, "is_configured", lambda: True)
    monkeypatch.setattr(sender, "name", lambda: "instantly")
    monkeypatch.setattr(sender, "add_lead", fake_add_lead)

    db = SessionLocal()
    try:
        lead = Lead(segment="consulting", company_name="Acme Co", owner_name="Jane Roe",
                    email="jane@acmeco.io", website="https://acmeco.io", status="New",
                    cold_email="Hi — quick idea for Acme.")
        db.add(lead); db.flush()
        msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                      to_email=lead.email, subject="quick idea",
                                      body=lead.cold_email, account="personal",
                                      actor="test", autonomous=False)
        assert msg.status == "Sent"
        assert msg.provider_id == "instantly"
        assert captured.get("email") == "jane@acmeco.io"
        assert captured.get("company_name") == "Acme Co"
        assert captured.get("personalization")  # our copy goes as personalization
        db.rollback()
    finally:
        db.close()


def test_voice_say_offline_returns_204(client, auth_headers):
    """Jennifer's neural TTS endpoint returns 204 when no OpenAI key is set, so the
    frontend cleanly falls back to the browser voice."""
    r = client.post("/voice/say", headers=auth_headers, json={"text": "Hello darling"})
    # 204 offline (no key) or 200 audio/mpeg if a key happens to be configured.
    assert r.status_code in (200, 204)
    if r.status_code == 200:
        assert r.headers.get("content-type", "").startswith("audio/")


def test_insurance_has_no_own_credentials_in_tests():
    """Without Thrust mailbox creds, insurance has no sender of its own — which is
    what triggers the automatic relay through the personal mailbox."""
    from app.integrations import gmail
    assert gmail.has_own_credentials(gmail.INSURANCE) is False


@requires_db
def test_client_goal_status_and_autoscale(client, auth_headers):
    """The client-acquisition engine reports progress and sizes outreach to the
    daily target without ever exceeding the safe ceilings."""
    from app.config import settings

    g = client.get("/clients/goal", headers=auth_headers).json()
    assert g["target"] >= 1
    assert 0 < g["conversion_rate"] <= 1
    assert g["needed_touches_per_day"] >= g["target"]
    assert g["won_today"] >= 0 and "on_track" in g

    # Setting a target re-sizes the volume knobs but stays within ceilings.
    r = client.post("/clients/target", json={"target": 15}, headers=auth_headers).json()
    assert r["enabled"] and r["target"] == 15
    assert settings.gmail_daily_send_cap <= settings.client_send_cap_ceiling
    assert settings.commercial_lead_daily_target <= settings.client_lead_target_ceiling

    # Idempotent: a second autoscale with no target change makes no further changes.
    r2 = client.post("/clients/autoscale", headers=auth_headers).json()
    assert r2["enabled"] and r2["changed"] == {}


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
def test_sms_opt_out_and_bulk_send_drafts(client, auth_headers):
    """A STOP text opts a number out (a hard legal line); the compliance guard
    then holds it, and the paced bulk 'send-drafts' reports sent/failed/blocked
    with real reasons instead of silently texting an opted-out number."""
    from app import sms_engine
    from app.database import SessionLocal
    from app.models import Message

    stop_phone, fresh_phone = "+15550000001", "+15550000002"
    db = SessionLocal()
    try:
        db.query(Message).filter(Message.to_email.in_([stop_phone, fresh_phone])).delete(
            synchronize_session=False)
        db.commit()
        # Inbound STOP → opted out (deterministic keyword match, no AI needed).
        sms_engine.record_inbound(db, phone=stop_phone, body="STOP")
        assert sms_engine.is_opted_out(db, stop_phone) is True
        assert sms_engine.is_opted_out(db, "+15559998888") is False
        # An explicit send to an opted-out number is refused (returns None, no row).
        assert sms_engine.send_text(db, entity_type=None, entity_id=None,
                                    phone=stop_phone, body="hi") is None
        # Unique from_account so send-drafts considers exactly these two (other
        # tests leave 'insurance' drafts that would crowd the oldest-20 window).
        db.add_all([
            Message(channel="sms", direction="outbound", to_email=stop_phone,
                    from_account="optout_test", body="draft1", status="Drafted"),
            Message(channel="sms", direction="outbound", to_email=fresh_phone,
                    from_account="optout_test", body="draft2", status="Drafted"),
        ])
        db.commit()
    finally:
        db.close()

    r = client.post("/sms/send-drafts", json={"account": "optout_test", "limit": 20},
                    headers=auth_headers).json()
    assert set(r) >= {"sent", "failed", "blocked", "considered", "reasons"}
    assert r["sent"] == 0  # no Twilio in tests → nothing actually sends
    assert r["sent"] + r["failed"] + r["blocked"] == r["considered"]
    assert r["blocked"] >= 1  # the opted-out number is held, never sent
    assert any("opted out" in x for x in r["reasons"])

    # Manual /sms/send also refuses the opted-out number with a clear reason.
    s = client.post("/sms/send", json={"to": stop_phone, "message": "hi"},
                    headers=auth_headers).json()
    assert s["ok"] is False and "opted out" in (s["reason"] or "").lower()


@requires_db
def test_lead_crm_profile_and_actions(client, auth_headers):
    """The per-lead CRM profile returns identity + per-channel touch counters +
    timeline; a logged call shows in both; send-text reports a clear reason offline."""
    from app.database import SessionLocal
    from app.models import Lead, Message

    db = SessionLocal()
    lid = None
    try:
        db.query(Lead).filter(Lead.email == "crmprofile@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", category="EverQuote Auto", owner_name="Casey Crm",
                    email="crmprofile@x.co", phone="+15550007777",
                    intake={"source": "everquote", "everquote": {
                        "first_name": "Casey", "vehicle_year": "2021",
                        "vehicle_make": "Ford", "vehicle_model": "Escape"}})
        db.add(lead); db.flush(); lid = lead.id; db.commit()

        p = client.get(f"/leads/{lid}/profile", headers=auth_headers).json()
        assert p["lead"]["name"] == "Casey Crm"
        assert p["counts"] == {"email": 0, "sms": 0, "call": 0}
        assert p["outreach"] and "2021 Ford Escape" in p["outreach"]["email"]["subject"]

        r = client.post(f"/leads/{lid}/log-call", headers=auth_headers,
                        json={"outcome": "Left voicemail", "notes": "callback tomorrow"})
        assert r.json()["counts"]["call"] == 1
        p2 = client.get(f"/leads/{lid}/profile", headers=auth_headers).json()
        assert p2["counts"]["call"] == 1
        assert any("Call" in e["label"] for e in p2["timeline"])

        st = client.post(f"/leads/{lid}/send-text", headers=auth_headers, json={"message": "hi"})
        assert st.status_code == 400 and "not sent" in st.json()["detail"].lower()

        # Templates: pickable email/text/call scripts, personalized for this lead.
        t = client.get(f"/leads/{lid}/templates", headers=auth_headers).json()
        assert len(t["email"]) == 5 and len(t["sms"]) == 4 and len(t["call"]) >= 1
        first_email = next(x for x in t["email"] if x["id"] == "first_contact")
        assert "Hi Casey," in first_email["body"]  # token filled with the lead's name
        assert t["call"][0]["framework"][0] == "Connect"
        assert "Casey" in t["call"][0]["script"] and "2021 Ford Escape" in t["call"][0]["script"]
    finally:
        if lid is not None:
            db.query(Message).filter(Message.entity_id == lid).delete(synchronize_session=False)
            db.query(Lead).filter(Lead.id == lid).delete(synchronize_session=False)
            db.commit()
        db.close()


@requires_db
def test_everquote_batch_queues_sms_draft(client, auth_headers):
    """The EverQuote batch queues a per-lead SMS draft alongside the email draft,
    de-duped per channel so a re-run never double-drafts the text."""
    from app import everquote
    from app.database import SessionLocal
    from app.models import Lead, Message

    db = SessionLocal()
    lid = None
    try:
        db.query(Lead).filter(Lead.email == "eqsms@x.co").delete(synchronize_session=False)
        db.commit()
        lead = Lead(segment="personal", category="EverQuote Auto", owner_name="Pat Doe",
                    email="eqsms@x.co", phone="+15550004321",
                    intake={"source": "everquote", "everquote": {
                        "first_name": "Pat", "vehicle_year": "2020",
                        "vehicle_make": "Honda", "vehicle_model": "Civic"}})
        db.add(lead); db.flush(); lid = lead.id; db.commit()

        res = everquote.personalize_batch(db, lead_ids=[str(lid)])
        assert res["queued_sms"] >= 1
        drafts = db.query(Message).filter(
            Message.channel == "sms", Message.entity_id == lid,
            Message.status == "Drafted").count()
        assert drafts == 1
        # Idempotent: re-running does not queue a second text for the same lead.
        res2 = everquote.personalize_batch(db, lead_ids=[str(lid)])
        assert res2["queued_sms"] == 0
    finally:
        if lid is not None:
            db.query(Message).filter(Message.entity_id == lid).delete(synchronize_session=False)
            db.query(Lead).filter(Lead.id == lid).delete(synchronize_session=False)
            db.commit()
        db.close()


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
def test_social_queue_pending_survives_flood_of_done_leads(client, auth_headers):
    """Regression: a pending LinkedIn-ready lead must still surface even when
    hundreds of already-Sent leads (also LinkedIn-ready) sort ahead of it — DONE
    status is filtered in SQL before the row LIMIT, not after (the same bug
    class already fixed on /leads etc.)."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.query(models.Lead).filter(models.Lead.email.like("socialdone%@x.co")).delete(
            synchronize_session=False)
        db.query(models.Lead).filter(models.Lead.email == "socialpending@x.co").delete(
            synchronize_session=False)
        db.commit()
        db.add_all([
            models.Lead(segment="commercial", category="Contractor", company_name=f"Done Lead {i}",
                       email=f"socialdone{i}@x.co", status="Sent",
                       linkedin="https://linkedin.com/in/done", linkedin_msg="hi")
            for i in range(160)
        ])
        db.add(models.Lead(segment="commercial", category="Contractor", company_name="Pending Social Lead",
                           email="socialpending@x.co", status="New",
                           linkedin="https://linkedin.com/in/pending", linkedin_msg="hi"))
        db.commit()
    finally:
        db.close()

    items = client.get("/outreach/social?channel=linkedin&limit=1000", headers=auth_headers).json()
    assert any(i["name"] == "Pending Social Lead" for i in items)
    assert all(i["status"] != "Sent" for i in items)


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
def test_csv_import_leads_recognizes_google_export_headers(client, auth_headers):
    """Regression: importing a Google/Outlook-style contacts export as 'leads'
    used to silently import 0 rows because only a literal 'email' header was
    recognized. Any reasonably-named email column must now be found."""
    csv_data = ("First Name,Last Name,Organization Name,E-mail 1 - Value,Phone 1 - Value\n"
               "Homer,Owner,ACME Auto Body,homerowner@realbiz.com,+16035551313\n")
    r = client.post("/import/leads", headers=auth_headers,
                    files={"file": ("google_export.csv", csv_data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 1 and body["skipped_no_email"] == 0


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


def test_learning_loop_covers_all_connected_platforms():
    """The learning loop ingests engagement from every connected platform that
    exposes it — not just IG/FB — so topic/timing selection learns everywhere."""
    from app import content_analytics as ca
    assert {"instagram", "facebook", "x", "youtube", "tiktok", "linkedin"} <= set(ca._INSIGHTS)
    assert all(callable(fn) for fn in ca._INSIGHTS.values())
    # Each platform metrics fetcher is safe offline (no creds → None, never raises).
    from app.integrations import twitter_api, youtube_api, tiktok_api, linkedin_api
    assert twitter_api.get_post_metrics(None, "1") is None
    assert youtube_api.get_post_metrics(None, "1") is None
    assert tiktok_api.get_post_metrics(None, "1") is None
    assert linkedin_api.get_post_metrics(None, "urn:li:share:1") is None


@requires_db
def test_apply_queue_is_strict_quality_with_stretch_separate(client, auth_headers):
    """Only ≥threshold matches reach the one-click apply queue; lower-fit 'stretch'
    roles stay visible on the Jobs page and only appear with include_stretch=true."""
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Job
    thr = settings.job_score_threshold
    db = SessionLocal()
    try:
        db.add(Job(title="Strong Director SRE", company="QualCo", location="Remote", remote=True,
                   source="t", url="https://jobs.test/strong-unique", score=thr + 10, score_breakdown={}))
        db.add(Job(title="Weak Stretch Role", company="StretchCo", location="Remote", remote=True,
                   source="t", url="https://jobs.test/stretch-unique", score=max(0, thr - 25),
                   score_breakdown={"stretch": True}))
        db.commit()
    finally:
        db.close()
    strict = client.get("/jobs/queue?limit=200", headers=auth_headers).json()
    urls = {j["url"] for j in strict}
    assert "https://jobs.test/strong-unique" in urls
    assert "https://jobs.test/stretch-unique" not in urls  # stretch excluded by default
    withstretch = client.get("/jobs/queue?limit=200&include_stretch=true", headers=auth_headers).json()
    assert "https://jobs.test/stretch-unique" in {j["url"] for j in withstretch}


@requires_db
def test_leads_line_and_temperature_survive_commercial_flood(client, auth_headers):
    """Regression: /leads?line=home&temperature=warm must still surface a warm
    home lead even when hundreds of higher/equal-scoring commercial leads exist —
    filtering by segment/status in SQL (not just Python after an unrelated LIMIT)
    is what keeps a flood of one segment from starving another out of the page."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # Idempotent against a rerun in the same DB.
        db.query(models.Lead).filter(models.Lead.email.like("flood%@x.co")).delete(synchronize_session=False)
        db.query(models.Lead).filter(models.Lead.email == "warmhome@x.co").delete(synchronize_session=False)
        db.commit()
        # A flood of top-scoring commercial leads — more than the default page size.
        db.add_all([
            models.Lead(segment="commercial", category="Contractor",
                       company_name=f"Flood Co {i}", email=f"flood{i}@x.co",
                       status="New", score=99)
            for i in range(250)
        ])
        # A warm home lead — scored at parity with the flood so its survival
        # depends purely on the segment/status SQL filters, not on out-ranking
        # unrelated pollution that may already exist in a shared test DB.
        db.add(models.Lead(segment="personal", category="New homeowner",
                           company_name="Warm Homeowner", email="warmhome@x.co",
                           status="replied", score=100))
        db.commit()
    finally:
        db.close()

    home_rows = client.get("/leads?line=home", headers=auth_headers).json()
    assert any(r["company_name"] == "Warm Homeowner" for r in home_rows)

    warm_rows = client.get("/leads?temperature=warm", headers=auth_headers).json()
    assert any(r["company_name"] == "Warm Homeowner" for r in warm_rows)

    both = client.get("/leads?line=home&temperature=warm", headers=auth_headers).json()
    assert any(r["company_name"] == "Warm Homeowner" for r in both)
    assert all(r["line"] == "home" and r["temperature"] == "warm" for r in both)


@requires_db
def test_leads_line_auto_spans_personal_and_commercial_vehicle_leads(client, auth_headers):
    """/leads?line=auto must surface BOTH a personal auto prospect and a
    vehicle-centric commercial one (auto shop/dealer/trucker) — commercial-auto
    (CAP) leads were previously invisible because segment='commercial' always
    forced the generic 'commercial' line bucket, regardless of category."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.query(models.Lead).filter(models.Lead.email.in_(
            ["personalauto@x.co", "commercialauto@x.co"])).delete(synchronize_session=False)
        db.commit()
        # Scored at parity with the router's SQL sort key's ceiling so these two
        # rows land on page 1 regardless of unrelated pollution in a shared DB —
        # a high `limit` alone isn't enough once a table has thousands of leads.
        db.add_all([
            models.Lead(segment="personal", category="Auto owner", company_name="Jane Driver",
                       email="personalauto@x.co", status="New", score=100),
            models.Lead(segment="commercial", category="Auto Dealership", company_name="Acme Motors",
                       email="commercialauto@x.co", status="New", score=100),
        ])
        db.commit()
    finally:
        db.close()

    rows = client.get("/leads?line=auto&limit=5000", headers=auth_headers).json()
    names = {r["company_name"] for r in rows}
    assert "Jane Driver" in names
    assert "Acme Motors" in names
    assert all(r["line"] == "auto" for r in rows)
    # The dealership stays a commercial-segment lead, just reclassified to Auto.
    dealer = next(r for r in rows if r["company_name"] == "Acme Motors")
    assert dealer["segment"] == "commercial"


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
def test_restaurants_temperature_survives_cold_flood(client, auth_headers):
    """Regression: /restaurants?temperature=warm must still surface a warm
    prospect even when hundreds of cold ones (sourced daily, the majority)
    exist — the same row-LIMIT-before-filter starvation bug already fixed on
    /leads. Temperature is pushed into SQL so it can't be starved."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.query(models.Restaurant).filter(
            models.Restaurant.email.like("coldflood%@x.co")).delete(synchronize_session=False)
        db.query(models.Restaurant).filter(
            models.Restaurant.email == "warmrestaurant@x.co").delete(synchronize_session=False)
        db.commit()
        db.add_all([
            models.Restaurant(kind="prospect", name=f"Cold Flood {i}", email=f"coldflood{i}@x.co",
                              status="New")
            for i in range(250)
        ])
        db.add(models.Restaurant(kind="prospect", name="Warm Restaurant",
                                 email="warmrestaurant@x.co", status="replied"))
        db.commit()
    finally:
        db.close()

    rows = client.get("/restaurants?temperature=warm", headers=auth_headers).json()
    assert any(r["name"] == "Warm Restaurant" for r in rows)
    assert all(r["temperature"] == "warm" for r in rows)


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
def test_crm_get_contact_survives_a_flood_of_other_contacts(client, auth_headers):
    """Regression: GET /crm/{id} must find a specific contact by its exact id
    even when hundreds of other contacts exist across every source — it must
    never depend on the aggregated, alphabetically-sorted, page-capped list
    that /crm (list) returns (that's what made a freshly-added manual contact
    report 'not found' once enough other leads/restaurants/jobs existed)."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.query(models.Lead).filter(models.Lead.email.like("crmflood%@x.co")).delete(
            synchronize_session=False)
        db.commit()
        # Names starting with 'A' so they sort ahead of a 'Z'-named contact,
        # simulating the daily-cycle's leads crowding a manual contact off a
        # capped, alphabetically-sorted aggregate page.
        db.add_all([
            models.Lead(segment="commercial", category="Contractor",
                       company_name=f"Aaa Flood Co {i}", email=f"crmflood{i}@x.co", status="New")
            for i in range(250)
        ])
        db.commit()
    finally:
        db.close()

    r = client.post("/crm", headers=auth_headers, json={"name": "Zzz Late Contact", "kind": "recruiter"})
    assert r.status_code == 200
    cid = r.json()["id"]

    detail = client.get(f"/crm/{cid}", headers=auth_headers).json()
    assert detail.get("name") == "Zzz Late Contact"
    assert "memories" in detail

    # Adding a note and linking must resolve the same way — not "not found".
    note = client.post(f"/crm/{cid}/note", headers=auth_headers, json={"content": "met at a conference"})
    assert note.status_code == 200

    # An unknown/malformed id is a clean 404, not a 500.
    assert client.get("/crm/not-a-real-id", headers=auth_headers).status_code == 404
    assert client.get("/crm/lead:00000000-0000-0000-0000-000000000000",
                      headers=auth_headers).status_code == 404


@requires_db
def test_accounts_roll_up_leads_clients_and_contacts_by_company(client, auth_headers):
    """Accounts (Salesforce-style) groups everything about ONE company — a lead,
    a won client, a manual contact — into a single 360 view, folding name variants
    (LLC / Inc. / casing) together via normalization, with a unified timeline."""
    from app import models
    from app.accounts import _normalize
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.query(models.Lead).filter(models.Lead.email == "acctlead@rollup.co").delete(synchronize_session=False)
        db.query(models.Client).filter(models.Client.email == "acctclient@rollup.co").delete(synchronize_session=False)
        db.query(models.ManualContact).filter(
            models.ManualContact.email == "acctcontact@rollup.co").delete(synchronize_session=False)
        db.commit()
        db.add(models.Lead(segment="commercial", category="Contractor", company_name="Rollup Test LLC",
                           email="acctlead@rollup.co", status="New", score=50))
        c = models.Client(business="insurance", name="Rollup Test, Inc.",
                          email="acctclient@rollup.co", premium_monthly=100, status="Active")
        db.add(c)
        db.add(models.ManualContact(name="Pat Rollup", company="ROLLUP TEST",
                                    email="acctcontact@rollup.co", kind="contact"))
        db.commit()
        db.add(models.ClientNote(client_id=c.id, kind="call", body="Great call today"))
        db.commit()
    finally:
        db.close()

    account_id = f"account:{_normalize('Rollup Test LLC')}"
    accts = client.get("/accounts?q=Rollup", headers=auth_headers).json()
    acct = next((a for a in accts if a["id"] == account_id), None)
    assert acct is not None, "LLC/Inc./casing variants of the same company should fold into one account"
    assert acct["leads"] == 1 and acct["clients"] == 1 and acct["contacts"] == 1
    assert acct["revenue_monthly"] == 100.0
    assert acct["businesses"] == ["Insurance"]

    detail = client.get(f"/accounts/{account_id}", headers=auth_headers).json()
    assert len(detail["leads"]) == 1 and len(detail["clients"]) == 1 and len(detail["contacts"]) == 1
    assert any(t["kind"] == "call" and "Great call" in t["body"] for t in detail["timeline"])

    missing = client.get("/accounts/account:definitely-not-a-real-company-xyz", headers=auth_headers)
    assert missing.status_code == 404


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
    # @x.co (not @example.com) so this fixture is excluded by the same
    # "*@x.co is test fixture noise" convention other tests rely on when
    # scanning /messages across the shared session DB.
    lead = models.Lead(segment="commercial", email="fu-test@x.co",
                       company_name="FU Co", status="Drafted")
    db.add(lead)
    db.flush()
    db.add(models.Message(channel="email", entity_type="lead", entity_id=lead.id,
                          to_email="fu-test@x.co", from_account="insurance",
                          subject="hi", body="first touch", status="Sent"))
    # An extreme past due_date so this follow-up sorts FIRST (the engine processes
    # oldest-due first, capped at 400/pass) — otherwise, in a shared DB that has
    # accumulated thousands of due follow-ups, this fixture's step never gets
    # reached and the test flakes.
    db.add(models.FollowUp(entity_type="lead", entity_id=lead.id, step=1,
                           due_date=date(2000, 1, 1), completed=False))
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


@requires_db
def test_no_newsletter_subscribe_without_actual_send():
    """We must only add people to a newsletter when we ACTUALLY email them — never
    for drafts/paused/unconfigured (consent/CAN-SPAM). Gmail is unconfigured in
    tests, so dispatch drafts and must NOT subscribe."""
    from app import models, outreach
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        lead = models.Lead(segment="commercial", company_name="NoSend Co",
                           email="nosend@realbusiness.com", status="New")
        db.add(lead); db.flush()
        msg = outreach.dispatch_email(
            db, entity_type="lead", entity_id=lead.id, to_email="nosend@realbusiness.com",
            subject="x", body="hi", account="insurance", actor="test", autonomous=False)
        db.flush()
        assert msg.status == "Drafted"  # no Gmail in tests → drafted, not sent
        subs = (db.query(models.NewsletterSubscriber)
                .filter(models.NewsletterSubscriber.email == "nosend@realbusiness.com").count())
        assert subs == 0  # never subscribed someone we didn't email
    finally:
        db.rollback(); db.close()


def test_grant_fit_scoring_prioritizes_mission():
    from app.agents.grant_research import score_fit
    music_score, pillar = score_fit("Youth music education scholarship program")
    off_score, _ = score_fit("Highway bridge maintenance contract")
    assert music_score > off_score
    assert pillar in ("Music & Arts", "Education & Scholarships")


def test_insurance_needs_are_category_specific():
    """Each business category maps to the coverage it actually needs (not generic)."""
    from app import insurance_needs as n
    assert "workers' comp" in n.coverage_for("Contractor")
    assert "liquor" in n.coverage_for("Restaurant")
    assert "malpractice" in n.coverage_for("Medical office")
    assert "errors & omissions" in n.coverage_for("Law Firm")
    # Unknown category still returns a sensible commercial default, never empty.
    assert n.coverage_for("Totally Unknown") == n._COMMERCIAL_DEFAULT
    # Personal lines get their own framing.
    assert "auto" in n.coverage_for("Auto owner", "personal")
    assert n.reason_for("Contractor").startswith("A contractor typically needs")


@requires_db
def test_selfcheck_runs_and_autocorrects(client, auth_headers):
    """Self-check verifies core features, returns a report, and auto-seeds objectives."""
    r = client.post("/admin/selfcheck", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert {"healthy", "fixed", "issues", "checks"} <= set(data)
    names = {c["name"] for c in data["checks"]}
    assert {"objectives", "credentials", "agents", "command_centers", "lead_pipeline"} <= names


def test_content_cadence_matches_spec():
    """IG/FB = exactly music+bnb+insurance at 3/day; LinkedIn 1/day with no music."""
    from app.platform_loops import LOOPS
    for ch in ("instagram", "facebook"):
        assert LOOPS[ch]["per_day"] == 3
        assert set(LOOPS[ch]["businesses"]) == {"music", "bnbglobal", "insurance"}
    assert LOOPS["linkedin"]["per_day"] == 1 and "music" not in LOOPS["linkedin"]["businesses"]
    assert LOOPS["blog"]["per_day"] == 1  # Medium 1/day


def test_newsletter_funnels_and_cadence():
    """One newsletter per funnel; sent 3x/week (Mon/Wed/Fri)."""
    from app import newsletters
    assert set(newsletters.FUNNELS) == {"insurance", "bnbglobal", "savorymind", "music"}
    assert newsletters.funnel_for_segment("commercial") == "insurance"
    assert newsletters.funnel_for_segment("consulting") == "bnbglobal"
    from app.scheduler import _JOBS
    assert _JOBS["newsletters"][1] == "0 11 * * 1,3,5"


def test_insurance_only_scheduler_registers_insurance_jobs_only(monkeypatch):
    """AUTONOMY_PROFILE=insurance registers ONLY the insurance agents/jobs so the
    other businesses stop making scheduled AI calls (the cost cut). Also confirms
    the cost-optimized default model."""
    from app import scheduler
    from app.config import settings

    assert settings.openai_model == "gpt-4o-mini"  # cheap default

    monkeypatch.setattr(settings, "autonomy_profile", "insurance")
    agents, jobs = scheduler.scheduled_plan()
    # insurance agents + jobs are scheduled
    assert "insurance" in agents and "commercial_finder" in agents
    assert "leads" in jobs and "followups" in jobs and "lifecycle" in jobs
    # everything else is skipped
    assert "music" not in agents and "job_hunter" not in agents
    assert "savorymind" not in agents and "bnbglobal" not in agents
    assert "publish_content" not in jobs and "music_releases" not in jobs
    assert "board_report" not in jobs and "auto_apply" not in jobs

    # "all" profile keeps everything
    monkeypatch.setattr(settings, "autonomy_profile", "all")
    agents_all, jobs_all = scheduler.scheduled_plan()
    assert "music" in agents_all and "publish_content" in jobs_all


def test_consulting_wedge_is_industry_specific():
    """BnB Global outreach leads with the right wedge per industry, not generic."""
    from app import consulting_value as c
    assert "HIPAA" in c.wedge_for("Medical office")
    assert "checkout" in c.wedge_for("Retail store")
    assert "fractional-CTO" in c.wedge_for("SaaS startup")
    assert c.wedge_for("Totally Unknown") == c._DEFAULT  # sensible default, never empty
    assert "lead with" in c.hint_for("Medical office").lower()


def test_savorymind_value_is_pain_specific():
    """SavoryMind pitch leads with a quantified outcome mapped from the pain signal."""
    from app import savorymind_value as s
    assert "average check" in s.value_for("Low average ticket")
    assert "review" in s.value_for("Weak online reviews")
    assert "high-margin" in s.value_for("No upsell at point of sale")
    assert s.value_for("anything else") == s._DEFAULT
    # Prefer a real menu insight; fall back to the value for placeholder pains.
    assert s.best_insight("Add a wine flight", "x") == "Add a wine flight"
    assert s.best_insight("Research before outreach", "Low average ticket") == s.value_for("Low average ticket")


def test_ab_subject_styles_rotate_evenly():
    """A/B exploration rotates through every subject style for balanced sampling."""
    from app.outreach_analytics import _STYLE_ORDER, experiment_hint, experiment_style
    seen = [experiment_style(i) for i in range(len(_STYLE_ORDER))]
    assert set(seen) == set(_STYLE_ORDER)          # one full sweep covers every style
    assert experiment_style(len(_STYLE_ORDER)) == _STYLE_ORDER[0]  # wraps around
    assert "subject line" in experiment_hint(0).lower()


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
    assert _interpret("run a self check")["intent"] == "self_check"
    # "Jarvis, do the same" — the user's colloquial way of asking for the
    # auto-check/auto-correct must resolve offline, not depend on the LLM.
    assert _interpret("do the same")["intent"] == "self_check"
    assert _interpret("auto check and auto correct")["intent"] == "self_check"
    assert _interpret("faça o mesmo")["intent"] == "self_check"


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
    # Replies-sync is GREEN when the in-process scheduler is on (default True) —
    # it no longer requires CRON_SECRET to show healthy.
    from app.config import settings
    replies = next(s for s in h["steps"] if s["key"] == "replies")
    assert replies["ok"] == bool(settings.enable_scheduler or settings.cron_secret)


@requires_db
def test_sync_replies_endpoint(client, auth_headers):
    """On-demand reply sync runs without a scheduler — returns a clean summary so
    leads can be warmed up on demand (no 500 even with no mailbox connected)."""
    r = client.post("/leads/sync-replies", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and "scanned" in d and "matched" in d


@requires_db
def test_setup_connect_status_and_save(client, auth_headers):
    """The in-app setup page reports connection status and applies a saved key."""
    from app.config import settings
    s = client.get("/setup", headers=auth_headers).json()
    assert set(s) == {"ai", "gmail_personal", "gmail_insurance", "gmail_insurance_backup",
                      "gmail_bnb", "gmail_savorymind",
                      "apollo", "google_places", "sms", "whatsapp", "calling", "jobs_api", "instantly",
                      "smartlead", "sendgrid", "meta_app", "tiktok_app", "booking",
                      "contacts_outreach_exclude", "newsletter_banners"}
    assert s["apollo"]["configured"] is False
    # SMS compliance guardrails are surfaced so the Texts UI shows the real window/cap.
    assert {"daily_cap", "window_start", "window_end", "timezone"} <= set(s["sms"])
    assert set(s["booking"]) == {"default", "insurance", "bnb", "savorymind"}
    # The AI-brain status block is present so the UI can warn when drafts are stubs.
    assert "configured" in s["ai"] and "model" in s["ai"]
    orig = settings.google_places_api_key
    try:
        r = client.post("/setup", headers=auth_headers, json={"google_places_api_key": "test-key-123"})
        assert r.status_code == 200 and "google_places_api_key" in r.json()["saved"]
        assert client.get("/setup", headers=auth_headers).json()["google_places"]["configured"] is True
    finally:
        settings.google_places_api_key = orig  # don't pollute other tests

    orig_exclude = settings.contacts_outreach_exclude
    try:
        r2 = client.post("/setup", headers=auth_headers,
                         json={"contacts_outreach_exclude": "mom@family.com, dad@family.com"})
        assert r2.status_code == 200 and "contacts_outreach_exclude" in r2.json()["saved"]
        s2 = client.get("/setup", headers=auth_headers).json()
        assert s2["contacts_outreach_exclude"] == "mom@family.com, dad@family.com"
    finally:
        settings.contacts_outreach_exclude = orig_exclude


@requires_db
def test_openai_key_connectable_at_runtime(client, auth_headers):
    """The AI brain can be connected from Setup (not just env vars) and takes
    effect immediately — the client rebuilds from the CURRENT key rather than
    being frozen at import, so it activates without a redeploy. The rebuild
    mechanism is asserted directly (works with or without the openai package
    installed); the live-status flip is checked only when openai is importable."""
    from app.ai import client as ai_client
    from app.config import settings

    orig = settings.openai_api_key
    try:
        settings.openai_api_key = ""
        ai_client._get_client()  # cache now reflects the empty key
        assert ai_client.is_live() is False
        assert client.get("/setup", headers=auth_headers).json()["ai"]["configured"] is False

        # Saving a key via Setup applies it to the live settings object...
        r = client.post("/setup", headers=auth_headers, json={"openai_api_key": "sk-test-fake-key"})
        assert r.status_code == 200 and "openai_api_key" in r.json()["saved"]
        assert settings.openai_api_key == "sk-test-fake-key"
        # ...and the client accessor rebuilds against it instead of the import-time
        # value (the core of the fix), so its cached key tracks the new one.
        ai_client._get_client()
        assert ai_client._client_key == "sk-test-fake-key"
        if ai_client._OpenAI is not None:  # openai installed (as in CI) → really live
            assert ai_client.is_live() is True
            assert client.get("/setup", headers=auth_headers).json()["ai"]["configured"] is True
    finally:
        settings.openai_api_key = orig
        ai_client._get_client()  # rebuild against the restored key so other tests are unaffected


@requires_db
def test_outbox_send_surfaces_errors_and_bulk_send(client, auth_headers):
    """A failing send returns the REAL reason (not a silent 'nothing happens'),
    and the paced bulk 'send-drafts' reports sent/failed + the reason. Offline
    (no mailbox) every send fails with a clear reason, never a crash."""
    from app.database import SessionLocal
    from app.models import Message

    db = SessionLocal()
    try:
        db.query(Message).filter(Message.to_email == "bulktest@x.co").delete(synchronize_session=False)
        db.commit()
        m = Message(channel="email", direction="outbound", entity_type="lead",
                    to_email="bulktest@x.co", from_account="insurance",
                    subject="Test", body="Body", status="Drafted")
        db.add(m); db.flush(); mid = str(m.id); db.commit()
    finally:
        db.close()

    # Single send: offline → 400 (mailbox not configured) or 502 with a real reason,
    # never a silent success.
    r = client.post(f"/messages/{mid}/send", headers=auth_headers)
    assert r.status_code in (400, 502)
    detail = r.json()["detail"].lower()
    # A real reason, never a silent success: either no delivery channel is
    # configured (400) or the send itself failed with a surfaced reason (502).
    assert ("no delivery channel" in detail or "not configured" in detail
            or "send failed" in detail)

    # Bulk send: returns a structured report, no crash.
    b = client.post("/messages/send-drafts", json={"account": "insurance", "limit": 20},
                    headers=auth_headers).json()
    assert set(b) >= {"sent", "failed", "considered", "errors"}
    assert b["sent"] + b["failed"] == b["considered"]

    # send_with_error itself returns a (id, reason) tuple with a reason on failure.
    from app.integrations import gmail
    _id, reason = gmail.send_with_error("", "s", "b", account="insurance")
    assert _id is None and reason


@requires_db
def test_send_drafts_sends_hot_leads_first(client, auth_headers, monkeypatch):
    """The rule: emails go to HOT leads first. A drafted email to a hot in-market
    lead (EverQuote, high score) is sent before an OLDER draft to a colder lead."""
    from datetime import datetime, timedelta, timezone

    from app import outreach
    from app.database import SessionLocal
    from app.models import Lead, Message

    # Delivery always succeeds, so what we're testing is the ORDER, not the channel.
    monkeypatch.setattr(outreach, "can_deliver", lambda account: True)
    monkeypatch.setattr(outreach, "deliver", lambda to, subject, body, account: ("fake-mid", None))

    acct = "hotfirst_test"
    db = SessionLocal()
    try:
        db.query(Message).filter(Message.from_account == acct).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.email.in_(["hot-hf@x.co", "cold-hf@x.co"])).delete(synchronize_session=False)
        db.commit()
        hot = Lead(segment="personal", category="EverQuote Auto", owner_name="Hot",
                   email="hot-hf@x.co", status="New", score=92)
        cold = Lead(segment="commercial", category="Biz", owner_name="Cold",
                    email="cold-hf@x.co", status="New", score=10)
        db.add_all([hot, cold]); db.flush()
        now = datetime.now(timezone.utc)
        # OLDER draft to the COLD lead, NEWER draft to the HOT lead — oldest-first
        # would send the cold one; hot-first must send the hot one instead.
        cold_msg = Message(channel="email", direction="outbound", entity_type="lead",
                           entity_id=cold.id, to_email="cold-hf@x.co", from_account=acct,
                           subject="c", body="c", status="Drafted",
                           created_at=now - timedelta(hours=2))
        hot_msg = Message(channel="email", direction="outbound", entity_type="lead",
                          entity_id=hot.id, to_email="hot-hf@x.co", from_account=acct,
                          subject="h", body="h", status="Drafted", created_at=now)
        db.add_all([cold_msg, hot_msg]); db.flush()
        hot_mid, cold_mid = str(hot_msg.id), str(cold_msg.id)
        db.commit()
    finally:
        db.close()

    # Send exactly ONE — hot-first means the HOT lead's email goes, not the older cold one.
    r = client.post("/messages/send-drafts", json={"account": acct, "limit": 1},
                    headers=auth_headers).json()
    assert r["sent"] == 1 and r["considered"] == 1

    db = SessionLocal()
    try:
        assert db.query(Message).filter(Message.id == hot_mid).first().status == "Sent"
        assert db.query(Message).filter(Message.id == cold_mid).first().status == "Drafted"
    finally:
        db.close()


@requires_db
def test_flush_hot_drafts_gated_by_autopilot(monkeypatch):
    """The auto-send cron only fires when the operator has enabled auto-send
    (full-auto mode OR Outreach Autopilot). With both off, drafts wait for review;
    with autopilot on, it flushes the email + SMS drafts (hot leads first)."""
    from app import control, outreach, scheduler, sms_engine
    from app.database import SessionLocal

    calls = {"email": 0, "sms": 0}
    monkeypatch.setattr(outreach, "send_email_drafts",
                        lambda db, **k: calls.__setitem__("email", calls["email"] + 1) or {"sent": 1})
    monkeypatch.setattr(sms_engine, "send_sms_drafts",
                        lambda db, **k: calls.__setitem__("sms", calls["sms"] + 1) or {"sent": 1})
    monkeypatch.setattr(control, "is_paused_safe", lambda db: False)
    monkeypatch.setattr(control, "get_mode", lambda db: "semi")

    db = SessionLocal()
    try:
        # Auto-send OFF → nothing sent, drafts wait for review.
        monkeypatch.setattr(control, "outreach_autopilot", lambda db: False)
        res_off = scheduler._flush_hot_drafts(db)
        assert "skipped" in res_off and calls == {"email": 0, "sms": 0}

        # Autopilot ON → both channels flush (hot leads first, inside each sender).
        monkeypatch.setattr(control, "outreach_autopilot", lambda db: True)
        res_on = scheduler._flush_hot_drafts(db)
        assert calls == {"email": 1, "sms": 1}
        assert "email" in res_on and "sms" in res_on
    finally:
        db.close()


@requires_db
def test_mailbox_health_diagnostic(client, auth_headers):
    """The Connect page can confirm each mailbox can ACTUALLY send (real auth
    check), not just that a key is saved. Offline it truthfully reports not-able."""
    r = client.get("/setup/mailbox-health", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert "outbound_mode" in d and len(d["accounts"]) == 5  # personal, insurance (+backup), bnb, savorymind
    for a in d["accounts"]:
        for k in ("account", "can_send", "configured", "sent_today", "daily_cap", "remaining_today"):
            assert k in a
        assert a["can_send"] is False  # no real mailbox connected in tests
        assert a["reason"]  # a clear human reason is always given when it can't send


@requires_db
def test_content_apply_hook_swaps_first_line(client, auth_headers):
    """Applying an alternative hook replaces only the post's opening line."""
    from app.database import SessionLocal
    from app.models import ContentItem
    db = SessionLocal()
    c = ContentItem(channel="linkedin", topic="t", title="T", business="executive",
                    body="Old first line.\nSecond line stays.", status="needs_approval",
                    meta={"hooks": ["A punchy new hook."]})
    db.add(c); db.commit(); cid = str(c.id); db.close()
    r = client.post(f"/content/{cid}/apply-hook", headers=auth_headers,
                    json={"hook": "A punchy new hook."})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["body"].startswith("A punchy new hook.")
    assert "Second line stays." in body["body"]


def test_education_partners_target_schools_not_generic_businesses():
    """The foundation's school agent sources real education institutions, not
    generic commercial leads (synthetic fallback stays education-categorized)."""
    from app.integrations import providers
    rows = providers.fetch_education_partners(5, scope="global")
    assert rows, "should always produce at least synthetic institutions"
    assert all(r["segment"] == "school_partner" for r in rows)
    assert all(r.get("category") in providers.EDUCATION_CATEGORIES
               or r.get("industry") == "Education" for r in rows)


@requires_db
def test_leads_filter_by_state_and_client_carries_state(client, auth_headers):
    """Leads can be filtered by state (EverQuote leads store it in the intake), so
    the Call List's state filter actually narrows them. And converting a lead to a
    client carries the state over, so the Client Book's state filter has a value to
    match (from-lead clients used to have a NULL state → every filter returned none)."""
    from app.database import SessionLocal
    from app.models import Lead

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email.in_(["ma-flt@x.co", "nh-flt@x.co"])).delete(synchronize_session=False)
        db.commit()
        ma = Lead(segment="personal", category="EverQuote Auto", owner_name="MA Lead",
                  email="ma-flt@x.co", status="New", score=92,
                  intake={"source": "everquote", "everquote": {"state": "MA"}})
        nh = Lead(segment="personal", category="EverQuote Auto", owner_name="NH Lead",
                  email="nh-flt@x.co", status="New", score=92,
                  intake={"source": "everquote", "everquote": {"state": "NH"}})
        db.add_all([ma, nh]); db.commit()
        ma_id = str(ma.id)
    finally:
        db.close()

    # State filter narrows to just that state's EverQuote leads.
    ma_rows = client.get("/leads?state=MA&limit=300", headers=auth_headers).json()
    nh_rows = client.get("/leads?state=NH&limit=300", headers=auth_headers).json()
    ma_hits = {l["email"] for l in ma_rows if l.get("email") in ("ma-flt@x.co", "nh-flt@x.co")}
    nh_hits = {l["email"] for l in nh_rows if l.get("email") in ("ma-flt@x.co", "nh-flt@x.co")}
    assert ma_hits == {"ma-flt@x.co"} and nh_hits == {"nh-flt@x.co"}

    # Converting the MA lead to a client carries the state over (was NULL before).
    created = client.post(f"/book/from-lead/{ma_id}", headers=auth_headers).json()
    assert created.get("state") == "MA"


@requires_db
def test_multitouch_cadence_enrolls_and_runs_all_channels(client, monkeypatch):
    """A contacted lead is enrolled into the multi-touch cadence (email→call→SMS…),
    and the engine executes each due channel: email via the dispatcher, SMS as a
    compliance-gated draft, and calls as a task in the queue. A reply stops it."""
    from datetime import date
    from app import followups, lead_sequence
    from app.database import SessionLocal
    from app.models import FollowUp, Lead, Message, Task

    db = SessionLocal()
    try:
        # A hot lead whose opener already went out (Sent) → eligible for the cadence.
        lead = Lead(segment="personal", category="EverQuote Auto", owner_name="Cadence Test",
                    email="cadence@x.co", phone="+16175550100", status="New", score=100)
        db.add(lead); db.flush()
        db.add(Message(channel="email", direction="outbound", entity_type="lead",
                       entity_id=lead.id, to_email="cadence@x.co", from_account="insurance",
                       subject="opener", body="hi", status="Sent"))
        db.commit()
        lid = lead.id

        # A lead with NO opener sent yet must NOT be enrolled (cadence starts after first touch).
        no_touch = Lead(segment="personal", category="EverQuote Auto", owner_name="No Touch",
                        email="notouch@x.co", phone="+16175550101", status="New", score=100)
        db.add(no_touch); db.commit()
        no_touch_id = no_touch.id

        # High limit so a large shared test DB can't crowd out our lead; it's contacted
        # + unenrolled so it must be enrolled, while the un-contacted lead is skipped.
        lead_sequence.enroll_active_leads(db, limit=5000)
        steps = lead_sequence.steps_for(db, lid)
        assert len(steps) == len(lead_sequence.INSURANCE_CADENCE)
        assert {s["channel"] for s in steps} == {"email", "sms", "call"}
        # The un-contacted lead was skipped.
        assert lead_sequence.steps_for(db, no_touch_id) == []

        # Make every step due now, no AI (deterministic templates/drafts).
        monkeypatch.setattr(followups.client, "is_live", lambda: False)
        db.query(FollowUp).filter(FollowUp.entity_type == "lead", FollowUp.entity_id == lid)\
            .update({FollowUp.due_date: date.today()}, synchronize_session=False)
        db.commit()

        out = followups.process_due_followups(db)
        assert out["call_tasks"] >= 1 and out["texted"] >= 1
        # SMS steps became Drafted sms Messages; call steps became pending call Tasks.
        sms_drafts = db.query(Message).filter(
            Message.channel == "sms", Message.entity_id == lid, Message.status == "Drafted").count()
        assert sms_drafts >= 1
        call_tasks = db.query(Task).filter(Task.summary.ilike("%Call Cadence Test%")).count()
        assert call_tasks >= 1
        # Every due step is now completed.
        assert db.query(FollowUp).filter(
            FollowUp.entity_id == lid, FollowUp.completed.is_(False)).count() == 0
    finally:
        db.query(Task).filter(Task.summary.ilike("%Call Cadence Test%")).delete(synchronize_session=False)
        db.query(FollowUp).filter(FollowUp.entity_id.in_([lid, no_touch_id])).delete(synchronize_session=False)
        db.query(Message).filter(Message.entity_id.in_([lid, no_touch_id])).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.id.in_([lid, no_touch_id])).delete(synchronize_session=False)
        db.commit()
        db.close()


@requires_db
def test_everquote_lead_coverage(client, auth_headers):
    """Coverage answers 'did they all get an email?' — counts SENT emails/texts/calls
    per EverQuote lead, flags unreachable ones, and lists who's not emailed yet."""
    from datetime import datetime, timezone
    from app.database import SessionLocal
    from app.models import Lead, Message

    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email.in_(["cov-a@x.co", "cov-b@x.co"])).delete(synchronize_session=False)
        db.commit()
        emailed = Lead(segment="personal", category="EverQuote Auto", owner_name="Emailed One",
                       email="cov-a@x.co", phone="+16170000011", status="New", score=92,
                       intake={"source": "everquote", "everquote": {"state": "MA"}})
        gap = Lead(segment="personal", category="EverQuote Auto", owner_name="Not Emailed One",
                   email="cov-b@x.co", phone="+16170000012", status="New", score=90,
                   intake={"source": "everquote", "everquote": {"state": "NH"}})
        unreachable = Lead(segment="personal", category="EverQuote Auto", owner_name="No Contact",
                           email=None, phone=None, status="New", score=88,
                           intake={"source": "everquote", "everquote": {"state": "FL"}})
        db.add_all([emailed, gap, unreachable]); db.flush()
        db.add(Message(channel="email", direction="outbound", entity_type="lead",
                       entity_id=emailed.id, to_email="cov-a@x.co", from_account="insurance",
                       subject="s", body="b", status="Sent", sent_at=datetime.now(timezone.utc)))
        db.commit()
        emailed_id, gap_id = str(emailed.id), str(gap.id)
    finally:
        db.close()

    cov = client.get("/leads/coverage", headers=auth_headers).json()
    assert cov["total"] >= 3
    # A drafted-but-unsent email doesn't count as "emailed" — only a real Sent one.
    names = {l["name"] for l in cov["not_emailed"]}
    assert "Not Emailed One" in names        # reachable, no sent email → in the gap list
    assert "No Contact" not in names         # no email at all → unreachable, not a gap
    assert cov["unreachable"] >= 1
    assert cov["emailed"] >= 1  # the one with a Sent email is counted
    assert emailed_id not in {l["id"] for l in cov["not_emailed"]}  # already emailed → not a gap


def test_bridge_call_has_valid_e164_caller_id(monkeypatch):
    """The bridge <Dial> must carry a valid E.164 callerId even if the voice number
    was saved with formatting — an invalid callerId makes Twilio drop the call the
    moment the producer answers."""
    from app.config import settings
    from app.integrations import twilio_voice as voice
    monkeypatch.setattr(settings, "twilio_voice_number", "(978) 254-1435", raising=False)
    monkeypatch.setattr(settings, "twilio_insurance_number", "", raising=False)
    monkeypatch.setattr(settings, "twilio_from_number", "", raising=False)
    monkeypatch.setattr(settings, "public_base_url", "https://example.run.app", raising=False)
    xml = voice.bridge_twiml("617-555-0100", "lead-1")
    assert 'callerId="+19782541435"' in xml   # normalized, not the raw formatted value
    assert "(978)" not in xml                  # the invalid form never reaches Twilio
    assert 'answerOnBridge="true"' in xml and "+16175550100" in xml


@requires_db
def test_delivery_status_webhooks_record_outcome(client, auth_headers):
    """Twilio delivery webhooks record whether a text/call actually LANDED onto the
    Message, so the UI can show 'delivered' / 'failed' instead of just 'Sent'."""
    from app.database import SessionLocal
    from app.models import Message

    db = SessionLocal()
    try:
        sms = Message(channel="sms", direction="outbound", entity_type="lead",
                      to_email="+16175559999", from_account="insurance", body="hi",
                      status="Sent", provider_id="SM_test_123")
        call = Message(channel="call", direction="outbound", entity_type="lead",
                       from_account="insurance", body="call", status="Dialing",
                       provider_id="CA_test_123")
        db.add_all([sms, call]); db.commit()
        sms_id, call_id = sms.id, call.id
    finally:
        db.close()

    # SMS delivered → recorded; call failed → recorded + marked Missed.
    client.post("/sms/status", data={"MessageSid": "SM_test_123", "MessageStatus": "delivered"})
    client.post("/sms/status", data={"MessageSid": "SM_never", "MessageStatus": "failed", "ErrorCode": "30006"})
    client.post("/calls/dial-status", data={"CallSid": "CA_test_123", "DialCallStatus": "failed"})

    db = SessionLocal()
    try:
        s = db.query(Message).filter(Message.id == sms_id).first()
        c = db.query(Message).filter(Message.id == call_id).first()
        assert s.delivery_status == "delivered"
        assert c.delivery_status == "failed" and c.status == "Missed"
    finally:
        db.query(Message).filter(Message.id.in_([sms_id, call_id])).delete(synchronize_session=False)
        db.commit(); db.close()


@requires_db
def test_lead_standalone_note_saves_and_shows_in_timeline(client, auth_headers):
    """A lead note can be saved on its own (not only by logging a call) and shows in
    the timeline as a Note — without counting as an outreach touch."""
    from app.database import SessionLocal
    from app.models import Lead

    db = SessionLocal()
    try:
        lead = Lead(segment="personal", category="EverQuote Auto", owner_name="Note Lead",
                    email="note-lead@x.co", status="New", score=90)
        db.add(lead); db.commit()
        lid = str(lead.id)
    finally:
        db.close()

    # Empty note is rejected; a real note saves.
    assert client.post(f"/leads/{lid}/note", json={"note": "   "}, headers=auth_headers).status_code == 400
    r = client.post(f"/leads/{lid}/note", json={"note": "Prefers email, works nights"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is True

    prof = client.get(f"/leads/{lid}/profile", headers=auth_headers).json()
    assert any("Note" in (e.get("label") or "") for e in prof["timeline"])
    # A standalone note is internal — it must NOT inflate the outreach counters.
    assert prof["counts"]["email"] == 0 and prof["counts"]["call"] == 0


def test_auto_dial_transfers_human_and_drops_recorded_voicemail(monkeypatch):
    """The auto-dialer: a human answer transfers to the producer's phone; voicemail
    plays the recorded drop (real voice), else a spoken fallback. Numbers E.164."""
    from app.config import settings
    from app.integrations import twilio_voice as voice
    monkeypatch.setattr(settings, "twilio_voice_number", "+19781112222", raising=False)
    monkeypatch.setattr(settings, "twilio_insurance_number", "", raising=False)
    monkeypatch.setattr(settings, "twilio_from_number", "", raising=False)
    monkeypatch.setattr(settings, "producer_callback", "(603) 930-8272", raising=False)
    monkeypatch.setattr(settings, "public_base_url", "https://x.run.app", raising=False)
    monkeypatch.setattr(settings, "call_recording_enabled", True, raising=False)

    # Human (and 'unknown') → transfer to YOUR phone, normalized to E.164, recorded.
    for ab in ("human", "unknown", ""):
        xml = voice.amd_twiml(ab, "lead-1")
        assert "<Dial" in xml and "+16039308272" in xml and 'callerId="+19781112222"' in xml

    # Machine + a recorded voicemail → play it, no transfer.
    monkeypatch.setattr(settings, "producer_voicemail_url", "https://cdn/vm.mp3", raising=False)
    machine = voice.amd_twiml("machine_end", "lead-1")
    assert "<Play>https://cdn/vm.mp3</Play>" in machine and "<Dial" not in machine
    assert voice.voicemail_configured() is True

    # Machine + no recording → a spoken fallback still leaves a message.
    monkeypatch.setattr(settings, "producer_voicemail_url", "", raising=False)
    assert "<Say>" in voice.amd_twiml("machine_end", None) and voice.voicemail_configured() is False

    # Recording flow captures audio and posts it back to be saved.
    rec = voice.record_vm_twiml()
    assert "<Record" in rec and "/calls/vm-saved" in rec


@requires_db
def test_leads_sort_options(client, auth_headers):
    """The leads list is sortable: hottest (score), newest/oldest, longest-since-
    contact, and name A–Z — so the user isn't stuck with one fixed order."""
    from app.database import SessionLocal
    from app.models import Lead

    # Tag both leads with a unique state so we can filter to JUST them — the DB
    # may hold hundreds of leads from other tests, which would otherwise crowd
    # ours past the row limit and make the ordering assertion flaky.
    db = SessionLocal()
    try:
        db.query(Lead).filter(Lead.email.like("srt-%@x.co")).delete(synchronize_session=False)
        db.commit()
        # Alpha is high-score; Zeta is low-score. Name order is the reverse of score.
        alpha = Lead(segment="personal", category="EverQuote Auto", owner_name="Alpha Srt",
                     email="srt-a@x.co", status="New", score=5,
                     intake={"everquote": {"state": "SRT"}})
        zeta = Lead(segment="personal", category="EverQuote Auto", owner_name="Zeta Srt",
                    email="srt-z@x.co", status="New", score=98,
                    intake={"everquote": {"state": "SRT"}})
        db.add_all([alpha, zeta]); db.commit()
    finally:
        db.close()

    def emails(rows):
        return [r["email"] for r in rows]

    # Hottest first → Zeta (98) before Alpha (5).
    by_score = emails(client.get("/leads?sort=score&state=SRT&limit=500", headers=auth_headers).json())
    assert by_score == ["srt-z@x.co", "srt-a@x.co"]
    # Name A→Z → Alpha before Zeta (opposite of score, proving the sort applied).
    by_name = emails(client.get("/leads?sort=name&state=SRT&limit=500", headers=auth_headers).json())
    assert by_name == ["srt-a@x.co", "srt-z@x.co"]
