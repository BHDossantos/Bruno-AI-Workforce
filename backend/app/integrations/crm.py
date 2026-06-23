"""HubSpot CRM push (Phase 2).

Stubbed so the pipeline runs without credentials. When ``HUBSPOT_API_KEY`` is
set, ``push_lead`` upserts a contact via the HubSpot CRM API. The Windsor.ai MCP
``hubspot`` connector is an alternative live path.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.crm")
_HUBSPOT_CONTACTS = "https://api.hubapi.com/crm/v3/objects/contacts"


def push_lead(lead: dict) -> dict:
    """Upsert a lead into HubSpot. Returns {ok, id|reason}."""
    if not settings.hubspot_api_key:
        log.info("HubSpot key not set — skipping CRM push for %s", lead.get("email"))
        return {"ok": False, "reason": "no_api_key"}
    props = {
        "email": lead.get("email"),
        "firstname": (lead.get("owner_name") or "").split(" ")[0],
        "lastname": " ".join((lead.get("owner_name") or "").split(" ")[1:]),
        "company": lead.get("company_name"),
        "phone": lead.get("phone"),
        "website": lead.get("website"),
        "industry": lead.get("industry"),
    }
    try:
        resp = httpx.post(
            _HUBSPOT_CONTACTS,
            headers={"Authorization": f"Bearer {settings.hubspot_api_key}"},
            json={"properties": props},
            timeout=20,
        )
        resp.raise_for_status()
        return {"ok": True, "id": resp.json().get("id")}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("HubSpot push failed: %s", exc)
        return {"ok": False, "reason": str(exc)}
