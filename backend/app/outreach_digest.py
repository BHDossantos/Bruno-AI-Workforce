"""Daily outreach digest — email the day's numbers so you know the machine is
working without opening the app.

Composes today's sends, replies, hot leads, goal progress and the top actions
from the read-only analytics the app already produces, renders a compact HTML
email, and sends it to REPORT_TO_EMAIL via the admin mailer. No outreach is sent
here — this is an internal status email to the operator.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import money_actions, outreach_performance
from .config import settings
from .integrations import mailer

log = logging.getLogger("bruno.outreach_digest")


def build(db: Session) -> dict:
    """The digest payload (also useful for an in-app preview).

    Order matters: run the pure reads first, then the cockpit LAST — it calls
    client_goal.status(), which can leave the session's transaction aborted, so no
    further DB reads may follow it on the same session. We reuse the goal it returns
    rather than querying it again."""
    perf = outreach_performance.report(db, days=7)
    cockpit = money_actions.actions(db)  # must be last DB read (status poisons tx)
    goal = cockpit.get("goal", {})
    hot = [h for h in cockpit.get("hot_leads", []) if h.get("temperature") == "hot"]
    deliver = None

    return {
        "goal": goal,
        "sent_7d": perf["totals"]["sent"],
        "replies_7d": perf["totals"]["replies"],
        "reply_rate": perf["totals"]["reply_rate"],
        "delivery_confirmed": perf["totals"].get("delivery_confirmed", 0),
        "delivery_unconfirmed": perf["totals"].get("delivery_unconfirmed", perf["totals"]["sent"]),
        "legacy_replied_undated": perf["totals"].get("legacy_replied_outbound_undated", 0),
        "sync_health": perf.get("sync_health", []),
        "warm": perf["totals"]["warm"],
        "hot": perf["totals"]["hot"],
        "actions": cockpit.get("actions", []),
        "hot_leads": hot[:8],
        "deliverability": deliver,
    }


def _html(d: dict) -> str:
    g = d["goal"]
    rows = "".join(
        f"<li><b>{a['title']}</b> — {a['why']}</li>" for a in d["actions"][:5]) or "<li>All caught up 🎉</li>"
    hot = "".join(
        f"<li>{h['name']} · {h.get('business','')}"
        + (f" · {h['line']}" if h.get('line') else "") + f" — ${h['value']:,}</li>"
        for h in d["hot_leads"]) or "<li>No hot leads yet — keep the sends flowing.</li>"
    deliver = ""
    if d["deliverability"]:
        dv = d["deliverability"]
        deliver = (f"<p><b>Delivery (7d):</b> {dv['delivered']:,} delivered "
                   f"({dv['delivered_rate']}%), {dv['open_rate']}% opened, {dv['bounce_rate']}% bounced.</p>")
    on_track = "✅ on track" if g.get("on_track") else f"⚠️ {g.get('deficit', 0)} to go"
    return (
        f"<h2>Your outreach — daily digest</h2>"
        f"<p><b>Client goal today:</b> {g.get('won_today', 0)} / {g.get('target', 0)} — {on_track}</p>"
        f"<p><b>Last 7 days:</b> {d['sent_7d']:,} recorded sends · {d['replies_7d']:,} observed inbound replies "
        f"· {d['warm']} warm · {d['hot']} hot leads.</p>"
        f"<p>{d.get('delivery_confirmed', 0)} have recorded delivery evidence; "
        f"{d.get('delivery_unconfirmed', d['sent_7d'])} do not. Sent is not delivered.</p>"
        f"<p>Reply coverage may be incomplete. {d.get('legacy_replied_undated', 0)} legacy outbound "
        f"records are marked Replied without a reply timestamp; they cannot be assigned to this window.</p>"
        f"{deliver}"
        f"<h3>Do these to get clients today</h3><ul>{rows}</ul>"
        f"<h3>Hot leads to close</h3><ul>{hot}</ul>"
        f"<p style='color:#888;font-size:12px'>Sent by your Bruno AI workforce. "
        f"Open the app for the full cockpit.</p>")


def send(db: Session) -> dict:
    """Build + email the digest to the operator. No-op (reported) if no recipient
    or mailer isn't configured."""
    to = settings.report_to_email or settings.admin_email
    if not to or to == "admin@example.com":
        return {"ok": False, "reason": "Set REPORT_TO_EMAIL to receive the digest."}
    d = build(db)
    sent = mailer.send_email(to=to, subject="Bruno AI — your daily outreach digest",
                             html=_html(d))
    return {"ok": bool(sent), "emailed": bool(sent), "to": to,
            "sent_7d": d["sent_7d"], "hot": d["hot"]}
