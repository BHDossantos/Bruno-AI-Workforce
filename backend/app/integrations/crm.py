"""HubSpot CRM push.

Upserts contacts into HubSpot. The access token comes from a **connected HubSpot
account** (the Connections platform) when present, otherwise from the
``HUBSPOT_API_KEY`` env var — so connecting HubSpot in the dashboard makes lead
sync start working with no redeploy. Safely no-ops when neither is configured.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import connectors

log = logging.getLogger("bruno.crm")
_HUBSPOT_CONTACTS = "https://api.hubapi.com/crm/v3/objects/contacts"


def resolve_token(db=None) -> str | None:
    """Prefer a connected HubSpot account's token; fall back to the env var."""
    creds = connectors.get_credentials(db, "hubspot") if db is not None else None
    if creds and creds.get("access_token"):
        return creds["access_token"]
    return settings.hubspot_api_key or None


def push_lead(lead: dict, db=None) -> dict:
    """Upsert a lead into HubSpot. Returns {ok, id|reason}."""
    token = resolve_token(db)
    if not token:
        log.info("No HubSpot token (connection or env) — skipping CRM push for %s",
                 lead.get("email"))
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
            headers={"Authorization": f"Bearer {token}"},
            json={"properties": props},
            timeout=20,
        )
        resp.raise_for_status()
        return {"ok": True, "id": resp.json().get("id")}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("HubSpot push failed: %s", exc)
        return {"ok": False, "reason": str(exc)}
