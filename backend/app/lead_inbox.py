"""Hands-free lead intake — import CSV lists emailed into a connected mailbox.

Email (or forward) a CSV to one of your connected Gmail mailboxes with a subject
that STARTS WITH the import tag (default "import"), and the scheduler imports the
attachment as leads on its next poll — no manual upload. The rest of the subject
becomes the lead category, so:

    Subject: "Import DOT Truckers"   ->  category "DOT Truckers"
    Subject: "import"                ->  category "Imported Leads"

Idempotent: every processed email is logged by its Gmail message id
(``ImportedEmailLog``), so the same CSV is never imported twice even though the
poller re-reads the inbox. A safe no-op when Gmail isn't connected.

Self-contained service module: the scheduler calls ``scan_and_import(db)``; all
Gmail specifics live in ``integrations/gmail.fetch_lead_csvs``.
"""
from __future__ import annotations

import csv
import io
import logging
import re

from . import importer
from .config import settings
from .integrations import gmail
from .models import ImportedEmailLog

log = logging.getLogger("bruno.lead_inbox")

# Header hints so a CSV with a preamble before the real header row still parses
# (mirrors routers.imports._csv_rows — DOT exports, Google/Outlook, etc.).
_HEADER_HINTS = ("email", "e-mail", "phone", "company", "name", "legal name")


def _enabled() -> bool:
    return str(getattr(settings, "lead_import_enabled", True)).strip().lower() in (
        "1", "true", "yes", "on")


def _tag() -> str:
    return (settings.lead_import_subject_tag or "import").strip().lower()


def _accounts() -> list[str]:
    """Mailboxes to scan: the configured one first (blank → insurance then personal),
    de-duped and limited to accounts that are actually connected."""
    want = (settings.lead_import_account or "").strip().lower()
    order = ([want] if want else []) + [gmail.INSURANCE, gmail.PERSONAL]
    seen: set[str] = set()
    out: list[str] = []
    for acct in order:
        if acct and acct not in seen and gmail.is_configured(acct):
            seen.add(acct)
            out.append(acct)
    return out


def _subject_matches(subject: str) -> bool:
    """Only act on deliberate imports: the subject must start with the tag, so a
    random CSV attachment in the inbox is never swept in."""
    return (subject or "").strip().lower().startswith(_tag())


def _category_from_subject(subject: str) -> str:
    """"Import DOT Truckers" -> "DOT Truckers"; bare "import" -> "Imported Leads"."""
    s = (subject or "").strip()
    if s.lower().startswith(_tag()):
        s = s[len(_tag()):]
    s = re.sub(r"^[\s:,\-–—]+", "", s)          # a separator after the tag
    s = re.sub(r"^leads?\s+", "", s, flags=re.I)  # a leading "leads"/"lead"
    return s.strip() or "Imported Leads"


def _rows(content: str) -> list[dict]:
    """Parse CSV text to dict rows, tolerant of a preamble before the header row."""
    lines = (content or "").splitlines()
    start = 0
    for i, ln in enumerate(lines[:10]):
        low = ln.lower()
        if "," in ln and any(h in low for h in _HEADER_HINTS):
            start = i
            break
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def scan_and_import(db) -> dict:
    """Import any new mailed-in lead CSVs. Returns a summary; never raises."""
    if not _enabled():
        return {"enabled": False, "messages": 0, "imported": 0, "updated": 0}
    lookback = int(getattr(settings, "lead_import_lookback_days", 30) or 30)
    total_imported = total_updated = msgs = 0
    for account in _accounts():
        for m in gmail.fetch_lead_csvs(account, newer_than_days=lookback):
            if not _subject_matches(m.get("subject", "")):
                continue
            mid = m.get("message_id")
            if not mid or db.query(ImportedEmailLog).filter_by(gmail_message_id=mid).first():
                continue  # already imported
            category = _category_from_subject(m.get("subject", ""))
            imported = updated = 0
            for att in m.get("attachments", []):
                try:
                    res = importer.process_leads_csv(
                        db, _rows(att.get("content", "")),
                        default_category=category, default_segment="commercial")
                    imported += int(res.get("imported", 0))
                    updated += int(res.get("updated", 0))
                except Exception:  # pragma: no cover - one bad file must not wedge the poll
                    log.exception("lead_inbox: import failed for %s", att.get("filename"))
            db.add(ImportedEmailLog(
                gmail_message_id=mid, account=account,
                subject=(m.get("subject") or "")[:300], category=category[:120],
                imported=imported, updated=updated))
            db.commit()
            total_imported += imported
            total_updated += updated
            msgs += 1
            log.info("lead_inbox: imported %d (+%d updated) as '%s' from %s msg %s",
                     imported, updated, category, account, mid)
    return {"enabled": True, "messages": msgs, "imported": total_imported, "updated": total_updated}
