"""Gmail integration — outbound send/draft + inbound reply reading.

Supports two sending identities:
- ``personal``  → ``GMAIL_ADDRESS`` (default brunodossantos707@gmail.com) — used by all agents.
- ``insurance`` → ``INSURANCE_GMAIL_ADDRESS`` (default bruno@thrustinsurance.com) — used by the Insurance agent.

Each account authenticates with OAuth2 via either a full authorized-user token
JSON or client id/secret + refresh token. Every function degrades gracefully
(returns None / [] and logs) when an account isn't configured, so the rest of
the system keeps working.

Mint a token per account with:  python -m app.scripts.gmail_auth <client_secret.json>
"""
from __future__ import annotations

import base64
import json
import logging
from email.mime.text import MIMEText

from ..config import settings

log = logging.getLogger("bruno.gmail")
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

PERSONAL = "personal"
INSURANCE = "insurance"


def _account_cfg(account: str) -> dict:
    if account == INSURANCE:
        return {
            "address": settings.insurance_gmail_address,
            "token_json": settings.insurance_google_token_json,
            "client_id": settings.insurance_google_oauth_client_id,
            "client_secret": settings.insurance_google_oauth_client_secret,
            "refresh_token": settings.insurance_google_oauth_refresh_token,
        }
    return {
        "address": settings.gmail_address,
        "token_json": settings.google_token_json,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "refresh_token": settings.google_oauth_refresh_token,
    }


def address_for(account: str = PERSONAL) -> str:
    return _account_cfg(account)["address"]


def _credentials(account: str):
    try:
        from google.oauth2.credentials import Credentials
    except Exception:  # pragma: no cover - dependency guard
        log.warning("google-auth not installed; Gmail disabled")
        return None

    cfg = _account_cfg(account)
    if cfg["token_json"]:
        try:
            return Credentials.from_authorized_user_info(json.loads(cfg["token_json"]), SCOPES)
        except Exception as exc:  # pragma: no cover
            log.warning("Invalid token JSON for account '%s': %s", account, exc)
            return None
    if cfg["client_id"] and cfg["refresh_token"]:
        return Credentials(
            token=None,
            refresh_token=cfg["refresh_token"],
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
    return None


def _service(account: str):
    creds = _credentials(account)
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build

        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as exc:  # pragma: no cover - network/dep guard
        log.warning("Could not build Gmail service for '%s': %s", account, exc)
        return None


def is_configured(account: str = PERSONAL) -> bool:
    return _credentials(account) is not None


def _raw(account: str, to: str, subject: str, body: str) -> dict:
    mime = MIMEText(body, "html")
    mime["to"] = to
    mime["from"] = address_for(account)
    mime["subject"] = subject or "(no subject)"
    return {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}


def send_message(to: str, subject: str, body: str, account: str = PERSONAL) -> str | None:
    """Send an email immediately from ``account``. Returns the message id or None."""
    svc = _service(account)
    if svc is None or not to:
        return None
    try:
        sent = svc.users().messages().send(userId="me", body=_raw(account, to, subject, body)).execute()
        return sent.get("id")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Gmail send failed (%s via %s): %s", to, account, exc)
        return None


def create_draft(to: str, subject: str, body: str, account: str = PERSONAL) -> str | None:
    """Create a draft in ``account`` for later review. Returns the draft id or None."""
    svc = _service(account)
    if svc is None or not to:
        return None
    try:
        draft = svc.users().drafts().create(
            userId="me", body={"message": _raw(account, to, subject, body)}
        ).execute()
        return draft.get("id")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Gmail draft failed (%s via %s): %s", to, account, exc)
        return None


def list_replies(newer_than_days: int = 3, account: str = PERSONAL) -> list[dict]:
    """Return recent inbound messages from ``account``: [{from_email, subject, snippet, thread_id}]."""
    svc = _service(account)
    if svc is None:
        return []
    try:
        query = f"in:inbox newer_than:{newer_than_days}d -category:promotions"
        resp = svc.users().messages().list(userId="me", q=query, maxResults=100).execute()
        out = []
        for ref in resp.get("messages", []):
            msg = svc.users().messages().get(
                userId="me", id=ref["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            out.append({
                "account": account,
                "from_email": _parse_email(headers.get("From", "")),
                "subject": headers.get("Subject", ""),
                "snippet": msg.get("snippet", ""),
                "thread_id": msg.get("threadId"),
            })
        return out
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Gmail list_replies failed (%s): %s", account, exc)
        return []


def _parse_email(from_header: str) -> str:
    """Extract the bare address from a 'Name <addr@x>' header."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<", 1)[1].split(">", 1)[0].strip().lower()
    return from_header.strip().lower()
