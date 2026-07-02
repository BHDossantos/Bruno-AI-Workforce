"""Accounts — the Salesforce-style "one page per company" view.

Salesforce rolls every Contact, Opportunity and Activity up under an Account so
a rep can see everything about a company in one place. We already track leads,
won clients, restaurant prospects and manual contacts as separate systems of
record (same pattern as crm.py) — Accounts groups them by normalized company
name into that same 360° roll-up, with no new sync table to keep consistent.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from .crm_pipeline import expected_value, stage_of
from .insurance_lines import LABELS, line_for
from .lead_temperature import classify
from .models import Client, ClientNote, Lead, ManualContact, Message, Restaurant

_SUFFIXES = re.compile(r"\b(llc|inc|corp|co|ltd|company|group|holdings)\b\.?", re.I)
_BIZ_LABEL = {"insurance": "Insurance", "bnb": "BnB Global",
             "savorymind": "SavoryMind", "music": "Music"}


def _normalize(name: str | None) -> str | None:
    """Fold "Acme LLC", "acme, inc." and "ACME" to the same URL-safe account key."""
    if not name or not name.strip():
        return None
    n = _SUFFIXES.sub(" ", name.lower())
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n or None


def _account_id(norm: str) -> str:
    return f"account:{norm}"


def _lead_business(lead: Lead) -> str:
    return "BnB Global" if lead.segment == "consulting" else "Insurance"


def list_accounts(db: Session, *, q: str | None = None, business: str | None = None,
                  limit: int = 200) -> list[dict]:
    """Every company we have ANY relationship with, rolled up: pipeline value,
    won revenue, and a cold/warm/hot mix — sorted by revenue then pipeline."""
    buckets: dict[str, dict] = {}

    def bucket(name: str | None) -> dict | None:
        norm = _normalize(name)
        if not norm:
            return None
        b = buckets.get(norm)
        if b is None:
            b = buckets[norm] = {
                "id": _account_id(norm), "name": name.strip(), "businesses": set(),
                "leads": 0, "clients": 0, "won": 0, "cold": 0, "warm": 0, "hot": 0,
                "pipeline_value": 0.0, "revenue_monthly": 0.0, "contacts": 0,
            }
        return b

    for lead in db.query(Lead).filter(Lead.company_name.isnot(None)).all():
        b = bucket(lead.company_name)
        if b is None:
            continue
        b["businesses"].add(_lead_business(lead))
        b["leads"] += 1
        b[classify(lead.status)] = b.get(classify(lead.status), 0) + 1
        b["pipeline_value"] += expected_value(lead)

    for r in db.query(Restaurant).filter(Restaurant.kind == "prospect", Restaurant.name.isnot(None)).all():
        b = bucket(r.name)
        if b is None:
            continue
        b["businesses"].add("SavoryMind")
        b["leads"] += 1
        b[classify(r.status)] = b.get(classify(r.status), 0) + 1

    for c in db.query(Client).all():
        b = bucket(c.name)
        if b is None:
            continue
        b["businesses"].add(_BIZ_LABEL.get(c.business, c.business or "Insurance"))
        b["clients"] += 1
        if (c.status or "").strip().lower() != "cancelled":
            b["won"] += 1
            b["revenue_monthly"] += float(c.premium_monthly or 0)

    for m in db.query(ManualContact).filter(ManualContact.company.isnot(None)).all():
        b = bucket(m.company)
        if b is None:
            continue
        b["contacts"] += 1

    out = []
    for b in buckets.values():
        b["businesses"] = sorted(b["businesses"])
        if business and business not in b["businesses"]:
            continue
        if q and q.lower() not in (b["name"] or "").lower():
            continue
        b["pipeline_value"] = round(b["pipeline_value"], 2)
        b["revenue_monthly"] = round(b["revenue_monthly"], 2)
        out.append(b)
    out.sort(key=lambda a: (a["revenue_monthly"], a["pipeline_value"]), reverse=True)
    return out[:limit]


def get_account(db: Session, account_id: str) -> dict | None:
    """The Account 360 view: every related lead/client/restaurant/contact, plus a
    unified activity timeline (client notes + every email to/from anyone here)."""
    if not account_id.startswith("account:"):
        return None
    norm = account_id[len("account:"):]

    def matches(name: str | None) -> bool:
        return bool(name) and _normalize(name) == norm

    leads = [l for l in db.query(Lead).filter(Lead.company_name.isnot(None)).all()
             if matches(l.company_name)]
    restaurants = [r for r in db.query(Restaurant).filter(
        Restaurant.kind == "prospect", Restaurant.name.isnot(None)).all() if matches(r.name)]
    clients = [c for c in db.query(Client).all() if matches(c.name)]
    contacts = [m for m in db.query(ManualContact).filter(
        ManualContact.company.isnot(None)).all() if matches(m.company)]
    if not (leads or restaurants or clients or contacts):
        return None

    lead_cards = [{
        "id": str(l.id), "type": "lead", "name": l.owner_name or l.company_name,
        "email": l.email, "phone": l.phone, "status": l.status, "stage": stage_of(l),
        "temperature": classify(l.status),
        "line": LABELS.get(line_for(l.category, l.segment, l.industry)),
        "value": expected_value(l),
        "link": "/bnbglobal" if l.segment == "consulting" else "/insurance",
    } for l in leads]

    client_cards = [{
        "id": str(c.id), "type": "client", "name": c.name, "email": c.email,
        "phone": c.phone, "business": _BIZ_LABEL.get(c.business, c.business),
        "line": c.line, "carrier": c.carrier, "status": c.status,
        "premium_monthly": float(c.premium_monthly or 0), "link": "/clients-crm",
    } for c in clients]

    restaurant_cards = [{
        "id": str(r.id), "type": "restaurant", "name": r.name, "email": r.email,
        "phone": r.phone, "status": r.status, "temperature": classify(r.status),
        "link": "/savorymind",
    } for r in restaurants]

    contact_cards = [{
        "id": str(m.id), "type": "contact", "name": m.name, "title": m.title,
        "email": m.email, "phone": m.phone, "kind": m.kind,
    } for m in contacts]

    timeline: list[dict] = []
    for c in clients:
        for note in db.query(ClientNote).filter(ClientNote.client_id == c.id).all():
            timeline.append({
                "at": note.created_at.isoformat() if note.created_at else None,
                "kind": note.kind, "body": note.body,
            })
    emails = {e for e in (
        [l.email for l in leads] + [c.email for c in clients]
        + [r.email for r in restaurants] + [m.email for m in contacts]) if e}
    if emails:
        for msg in (db.query(Message).filter(Message.to_email.in_(emails))
                    .order_by(Message.created_at.desc()).limit(100).all()):
            at = msg.sent_at or msg.created_at
            timeline.append({
                "at": at.isoformat() if at else None,
                "kind": f"email-{msg.direction}", "body": msg.subject or (msg.body or "")[:200],
            })
    timeline.sort(key=lambda t: t["at"] or "", reverse=True)

    display_name = (clients[0].name if clients else None) or (leads[0].company_name if leads else None) \
        or (restaurants[0].name if restaurants else None) or (contacts[0].company if contacts else None)
    businesses = sorted({*(_lead_business(l) for l in leads),
                        *(["SavoryMind"] if restaurants else []),
                        *(_BIZ_LABEL.get(c.business, c.business) for c in clients)})

    return {
        "id": account_id, "name": display_name, "businesses": businesses,
        "pipeline_value": round(sum(card["value"] for card in lead_cards), 2),
        "revenue_monthly": round(sum(c.premium_monthly or 0 for c in clients
                                    if (c.status or "").strip().lower() != "cancelled"), 2),
        "leads": lead_cards, "clients": client_cards, "restaurants": restaurant_cards,
        "contacts": contact_cards, "timeline": timeline[:100],
    }
