"""Insurance research and book-review projections. Never dispatches outreach."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select

from . import compliance
from .models import Client, ConversationOutcome, InsuranceProspectReview, Lead

SEGMENTS = ("commercial", "personal", "referral_partner")
LIMIT = 200


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def review_flags(review, suppressed, now):
    flags = ["outreach_authorization_and_licensed_handler_review_required"]
    if suppressed:
        flags.append("do_not_contact")
    if not review:
        return flags + ["source_and_contact_evidence_missing", "renewal_unknown"]
    contacts = review.get("contacts", [])
    verified = [c for c in contacts if c["status"] == "verified"
                and _utc(datetime.fromisoformat(c["checked_at"])) >= now - timedelta(days=30)]
    if not verified:
        flags.append("decision_maker_contact_not_recently_verified")
    if _utc(datetime.fromisoformat(review["observed_at"])) < now - timedelta(days=90):
        flags.append("source_evidence_stale")
    if not review.get("renewal_date"):
        flags.append("renewal_unknown")
    return flags


def prospects(db, now):
    query = select(Lead).where(Lead.segment.in_(SEGMENTS))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    leads = db.scalars(query.order_by(case((Lead.segment == "commercial", 0), else_=1),
                                       Lead.created_at.desc(), Lead.id).limit(LIMIT)).all()
    reviews = {r.lead_id: r for r in db.scalars(select(InsuranceProspectReview).where(
        InsuranceProspectReview.lead_id.in_([l.id for l in leads])))} if leads else {}
    items = []
    for lead in leads:
        row = reviews.get(lead.id)
        review = row.payload if row else None
        suppressed = compliance.is_dnc(db, phone=lead.phone, email=lead.email) or any(
            compliance.is_dnc(db, phone=c["phone"]) for c in (review or {}).get("contacts", []))
        items.append({"lead_id": str(lead.id), "name": lead.company_name or lead.owner_name or "Unnamed lead",
                      "segment": lead.segment, "phone": lead.phone, "email": lead.email,
                      "source": review["source_kind"] if review else "unattributed",
                      "review_revision": row.revision if row else 0, "review": review,
                      "review_flags": review_flags(review, suppressed, now), "suppressed": suppressed})
    # Renewal evidence only prioritizes within the clearly bounded recent-lead
    # sample. Formation/registration dates are never treated as policy renewals.
    items.sort(key=lambda r: (r["suppressed"],
        not bool((r["review"] or {}).get("renewal_date")),
        (r["review"] or {}).get("renewal_date") or "9999", r["segment"] != "commercial"))
    return {"total": total, "limit": LIMIT, "items": items}


def cross_sell(db):
    eligible = (Client.business == "insurance", Client.status.in_(("Active", "Renewed")))
    total = db.scalar(select(func.count()).select_from(Client).where(*eligible)) or 0
    rows = db.scalars(select(Client).where(*eligible).order_by(
        Client.expires_at.asc().nullslast(), Client.id).limit(LIMIT)).all()
    lead_ids = {r.lead_id for r in rows if r.lead_id}
    # Join only explicit lead identities. Shared email/phone is not proof that
    # unrelated people or companies have the same insurance policies.
    related = db.scalars(select(Client).where(*eligible, Client.lead_id.in_(lead_ids))).all() if lead_ids else []
    groups = {}
    for row in related:
        groups.setdefault(row.lead_id, []).append(row)
    items, seen = [], set()
    for row in rows:
        key = ("lead", row.lead_id) if row.lead_id else ("client", row.id)
        if key in seen:
            continue
        seen.add(key)
        book = groups.get(row.lead_id, [row]) if row.lead_id else [row]
        lines = sorted({c.line.strip().lower() for c in book if c.line and c.line.strip()})
        suppressed = any(compliance.is_dnc(db, phone=c.phone, email=c.email) for c in book)
        lead = db.get(Lead, row.lead_id) if row.lead_id else None
        if lead:
            suppressed = suppressed or compliance.is_dnc(db, phone=lead.phone, email=lead.email)
        questions = []
        if "commercial" in lines:
            if "auto" not in lines:
                questions.append("Would you like a licensed producer to review your personal auto coverage?")
            if "home" not in lines:
                questions.append("Would you like a licensed producer to review your home or renters coverage?")
        elif any(line in lines for line in ("auto", "home", "life", "renters")):
            questions.append("Do you own a business, and would you like a licensed producer to review its coverage?")
        else:
            questions.append("Confirm which policies are currently held before suggesting another coverage review.")
        questions.append("Would you like to share our contact details with someone who wants a review?")
        expirations = [c.expires_at for c in book if c.expires_at]
        items.append({"client_id": str(row.id), "name": row.name,
                      "lead_id": str(row.lead_id) if row.lead_id else None,
                      "recorded_lines": lines, "questions": [] if suppressed else questions,
                      "expires_at": min(expirations).isoformat() if expirations else None,
                      "suppressed": suppressed})
    return {"total_records": total, "limit": LIMIT, "items": items,
            "basis": "recorded_active_client_policies_not_complete_coverage"}


def funnel(db, days, now):
    start = now - timedelta(days=days)
    # Aggregate once per lead, not per touch. This is a recorded-event window,
    # not a claim that an answer preceded a quote or that a carrier issued cover.
    c = ConversationOutcome
    rows = db.execute(select(c.lead_id,
        func.sum(case((c.method == "call", 1), else_=0)).label("attempts"),
        func.max(case(((c.method == "call") & (c.outcome == "answered"), 1), else_=0)).label("answered"),
        func.max(case((c.quote_sent.is_(True), 1), else_=0)).label("quoted"),
        func.max(case((c.conversation_status == "sold", 1), else_=0)).label("sold"),
        func.sum(case(((c.method == "call") & c.outcome.in_(("wrong_number", "disconnected", "invalid_number")), 1), else_=0)).label("invalid")
    ).join(Lead, Lead.id == c.lead_id).where(Lead.segment.in_(SEGMENTS),
        c.created_at >= start, c.created_at <= now).group_by(c.lead_id)).all()
    sources = {r.lead_id: r.payload.get("source_kind", "unattributed") for r in db.scalars(
        select(InsuranceProspectReview).where(InsuranceProspectReview.lead_id.in_([r.lead_id for r in rows])))} if rows else {}
    counts = {k: 0 for k in ("call_attempts", "answered_leads", "quoted_leads", "sold_leads",
                             "answered_and_quoted_leads", "quoted_and_sold_leads", "invalid_number_attempts")}
    by_source = {}
    for row in rows:
        source = sources.get(row.lead_id, "unattributed")
        group = by_source.setdefault(source, {"source": source, "call_attempts": 0,
            "answered_leads": 0, "quoted_leads": 0, "sold_leads": 0})
        for key, value in (("call_attempts", row.attempts), ("answered_leads", row.answered),
                           ("quoted_leads", row.quoted), ("sold_leads", row.sold)):
            counts[key] += int(value or 0)
            group[key] += int(value or 0)
        counts["answered_and_quoted_leads"] += int(bool(row.answered and row.quoted))
        counts["quoted_and_sold_leads"] += int(bool(row.quoted and row.sold))
        counts["invalid_number_attempts"] += int(row.invalid or 0)
    def rate(n, d):
        return round(counts[n] / counts[d], 4) if counts[d] else None
    return {"days": days, "period_start": start.isoformat(), "period_end": now.isoformat(),
            "basis": "distinct_insurance_leads_with_recorded_outcomes", **counts,
            "answer_to_quote_rate": rate("answered_and_quoted_leads", "answered_leads"),
            "quote_to_sale_rate": rate("quoted_and_sold_leads", "quoted_leads"),
            "by_source": sorted(by_source.values(), key=lambda r: r["source"]),
            "source_attribution": "current_review_source_not_historical_acquisition",
            "verification": "operator_reported_not_carrier_verified"}
