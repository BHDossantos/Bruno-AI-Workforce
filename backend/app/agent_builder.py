"""Create an AI sales agent from a business URL.

Fetches the site, strips it to text, and asks the model to produce the offer, ICP,
target industries, pain points, outreach angles and ready-to-use message scripts —
then persists it as an AgentBlueprint. This is the "Create Agent from URL" feature
(Instantly/Smartlead). Degrades gracefully: returns a clear error if the site can't
be fetched or no OpenAI key is set.
"""
from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.orm import Session

from .ai import client
from .ai.prompts import AGENT_FROM_URL
from .models import AgentBlueprint

log = logging.getLogger("bruno.agent_builder")

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _fetch_text(url: str, limit: int = 6000) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    r = httpx.get(url, timeout=20, follow_redirects=True,
                  headers={"User-Agent": "Mozilla/5.0 (BrunoAI agent-builder)"})
    r.raise_for_status()
    html = r.text or ""
    html = _TAG.sub(" ", html)
    text = _WS.sub(" ", _HTML.sub(" ", html)).strip()
    return text[:limit]


def build_from_url(db: Session, url: str) -> dict:
    """Generate + persist an AgentBlueprint for a business URL."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "Enter a business URL."}
    try:
        site_text = _fetch_text(url)
    except Exception as exc:
        return {"ok": False, "error": f"Couldn't read that site: {str(exc)[:120]}"}
    if not site_text:
        return {"ok": False, "error": "That site had no readable text."}
    if not client.is_live():
        return {"ok": False, "error": "Set OPENAI_API_KEY to generate the agent."}

    data = client.complete_json(AGENT_FROM_URL.format(url=url, site_text=site_text))
    if not isinstance(data, dict) or not data:
        return {"ok": False, "error": "Generation failed — try again."}

    industries = data.get("industries")
    if isinstance(industries, list):
        industries = ", ".join(str(i) for i in industries)
    bp = AgentBlueprint(
        url=url, business=data.get("business"), offer=data.get("offer"),
        icp=data.get("icp"), industries=industries,
        pain_points=data.get("pain_points"), angles=data.get("angles"),
        scripts=data.get("scripts") if isinstance(data.get("scripts"), dict) else None,
    )
    db.add(bp)
    db.commit()
    db.refresh(bp)
    return {"ok": True, **_serialize(bp)}


def _serialize(bp: AgentBlueprint) -> dict:
    return {
        "id": str(bp.id), "url": bp.url, "business": bp.business, "offer": bp.offer,
        "icp": bp.icp, "industries": bp.industries, "pain_points": bp.pain_points,
        "angles": bp.angles, "scripts": bp.scripts or {},
        "created_at": bp.created_at.isoformat() if bp.created_at else None,
    }


def list_blueprints(db: Session, limit: int = 50) -> list[dict]:
    rows = db.query(AgentBlueprint).order_by(AgentBlueprint.created_at.desc()).limit(limit).all()
    return [_serialize(b) for b in rows]
