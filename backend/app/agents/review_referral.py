"""Review & Referral Agent — turns won policies into reviews and new leads.

After a policy is won, asks the happy client for (1) a Google review and (2) a
referral. Each won client is asked once (tracked via the action log), routed
through the Thrust mailbox. Set GOOGLE_REVIEW_LINK so the ask includes the link.
"""
from __future__ import annotations

import logging

from ..ai import client, skills
from ..ai.prompts import REVIEW_REQUEST
from ..config import settings
from ..models import ActionLog, Lead
from .base import BaseAgent

log = logging.getLogger("bruno.agents.review_referral")

_ASKED = "review_requested"


class ReviewReferralAgent(BaseAgent):
    key = "review_referral"
    name = "Review & Referral Agent"
    description = ("After every won policy, requests a Google review and asks the happy "
                   "client for a referral.")
    schedule_cron = "0 12 * * *"  # daily midday

    def execute(self) -> dict:
        # Won leads we haven't already asked.
        asked = {eid for (eid,) in self.db.query(ActionLog.entity_id)
                 .filter(ActionLog.action == _ASKED).all() if eid}
        won = (self.db.query(Lead)
               .filter(Lead.status == "Closed Won", Lead.email.isnot(None))
               .order_by(Lead.created_at.desc()).limit(100).all())
        targets = [l for l in won if str(l.id) not in asked]

        review_line = (f"Google review link to include: {settings.google_review_link}"
                       if settings.google_review_link else
                       "No Google review link is configured — ask for a review in general terms.")
        sysp = skills.system_prompt("cold-email")
        sent = 0
        for l in targets:
            try:
                name = l.owner_name or l.company_name or "there"
                art = client.complete_json(
                    REVIEW_REQUEST.format(name=name, review_line=review_line), system=sysp)
                art = art if isinstance(art, dict) else {}
                subject = art.get("subject") or "Quick favor — and thank you!"
                body = art.get("body")
                msg = self.dispatch_email(entity_type="lead", entity_id=l.id, to_email=l.email,
                                          subject=subject, body=body, account="insurance")
                self.log_action(_ASKED, entity="lead", entity_id=l.id,
                                detail={"status": msg.status})
                if msg.status in ("Sent", "Drafted"):
                    sent += 1
                self.db.commit()
            except Exception:  # one failure must not stop the rest
                log.exception("review/referral ask failed for %s", l.email)
                self.db.rollback()

        return {"summary": f"Review & Referral Agent: asked {sent} won client(s) for a "
                f"review + referral ({len(targets)} eligible).",
                "asked": sent, "eligible": len(targets)}
