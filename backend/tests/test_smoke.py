"""End-to-end smoke tests for the Bruno AI Workforce backend."""
from app.agents import AGENTS
from app.agents.insurance import InsuranceAgent
from app.agents.job_hunter import JobHunterAgent
from app.agents.music import MusicAgent

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
