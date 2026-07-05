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
INSURANCE_BACKUP = "insurance_backup"
BNB = "bnb"
SAVORYMIND = "savorymind"


def _account_cfg(account: str) -> dict:
    if account == INSURANCE:
        return {
            "address": settings.insurance_gmail_address,
            "token_json": settings.insurance_google_token_json,
            "client_id": settings.insurance_google_oauth_client_id,
            "client_secret": settings.insurance_google_oauth_client_secret,
            "refresh_token": settings.insurance_google_oauth_refresh_token,
            "app_password": settings.insurance_gmail_app_password,
        }
    if account == INSURANCE_BACKUP:
        return {
            "address": settings.insurance_backup_gmail_address,
            "token_json": settings.insurance_backup_google_token_json,
            "client_id": settings.insurance_backup_google_oauth_client_id,
            "client_secret": settings.insurance_backup_google_oauth_client_secret,
            "refresh_token": settings.insurance_backup_google_oauth_refresh_token,
            "app_password": settings.insurance_backup_gmail_app_password,
        }
    if account == BNB:
        return {
            "address": settings.bnb_gmail_address,
            "token_json": settings.bnb_google_token_json,
            "client_id": settings.bnb_google_oauth_client_id,
            "client_secret": settings.bnb_google_oauth_client_secret,
            "refresh_token": settings.bnb_google_oauth_refresh_token,
            "app_password": settings.bnb_gmail_app_password,
        }
    if account == SAVORYMIND:
        return {
            "address": settings.savorymind_gmail_address,
            "token_json": settings.savorymind_google_token_json,
            "client_id": settings.savorymind_google_oauth_client_id,
            "client_secret": settings.savorymind_google_oauth_client_secret,
            "refresh_token": settings.savorymind_google_oauth_refresh_token,
            "app_password": settings.savorymind_gmail_app_password,
        }
    return {
        "address": settings.gmail_address,
        "token_json": settings.google_token_json,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "refresh_token": settings.google_oauth_refresh_token,
        "app_password": settings.gmail_app_password,
    }


def address_for(account: str = PERSONAL) -> str:
    return _account_cfg(account)["address"]


def account_for_segment(segment: str | None) -> str:
    """Which mailbox sends for a given lead segment. Consulting uses its own BnB
    mailbox when connected, else falls back to personal; insurance segments use the
    insurance mailbox; everything else uses personal."""
    if segment == "consulting" and is_configured(BNB):
        return BNB
    if segment in ("commercial", "personal"):
        return INSURANCE
    return PERSONAL


def restaurant_account() -> str:
    """Mailbox for SavoryMind restaurant outreach: its own when connected, else personal."""
    return SAVORYMIND if is_configured(SAVORYMIND) else PERSONAL


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


def _smtp_login(account: str):
    """Return (login_address, login_password, from_address, reply_to) for SMTP.

    Normally an account logs in and sends as itself. The insurance account, when
    its own Thrust credentials aren't available, can send THROUGH the personal
    mailbox in one of two ways:
      - send_as_alias: From = Thrust address (needs a verified Gmail alias)
      - via_personal_reply_to: From = personal address, Reply-To = Thrust (no
        Thrust access needed at all; replies still land in the Thrust inbox)
    """
    cfg = _account_cfg(account)
    # Insurance relay requested EXPLICITLY → always send through the personal mailbox,
    # even if the insurance account has its own (possibly broken/blocked) App Password.
    # This is what lets "send insurance through my personal mailbox" actually work
    # without first deleting a bad Thrust password.
    if account == INSURANCE and (settings.insurance_send_as_alias or settings.insurance_via_personal_reply_to):
        p = _account_cfg(PERSONAL)
        if p.get("app_password") and p.get("address"):
            if settings.insurance_send_as_alias:
                return p["address"], p["app_password"], cfg["address"], None
            return p["address"], p["app_password"], p["address"], cfg["address"]
    # Otherwise send as the account itself.
    if cfg.get("app_password") and cfg.get("address"):
        return cfg["address"], cfg["app_password"], cfg["address"], None
    # Insurance with no usable creds of its own → fall back to the personal relay.
    if account == INSURANCE:
        p = _account_cfg(PERSONAL)
        if p.get("app_password") and p.get("address"):
            if settings.insurance_send_as_alias:
                return p["address"], p["app_password"], cfg["address"], None
            if settings.insurance_via_personal_reply_to:
                return p["address"], p["app_password"], p["address"], cfg["address"]
    return None, None, None, None


def _smtp_configured(account: str) -> bool:
    return _smtp_login(account)[1] is not None


def is_configured(account: str = PERSONAL) -> bool:
    """Configured if EITHER OAuth credentials OR an SMTP app password is set."""
    return _credentials(account) is not None or _smtp_configured(account)


def has_own_credentials(account: str = PERSONAL) -> bool:
    """True if this account can send AS ITSELF (its own OAuth token or App
    Password) — i.e. without relaying through another mailbox. Used to decide
    whether insurance must fall back to sending through the personal mailbox."""
    cfg = _account_cfg(account)
    return _credentials(account) is not None or bool(cfg.get("app_password") and cfg.get("address"))


def _send_smtp(account: str, to: str, subject: str, body: str) -> str | None:
    """Send via Gmail SMTP using an App Password. Returns a synthetic id or None."""
    import smtplib
    from email.utils import make_msgid

    login_addr, pw, from_addr, reply_to = _smtp_login(account)
    if not (login_addr and pw):
        return None
    mime = MIMEText(body, "html")
    mime["To"] = to
    mime["From"] = from_addr or login_addr
    mime["Subject"] = subject or "(no subject)"
    if reply_to:
        mime["Reply-To"] = reply_to
    msg_id = make_msgid()
    mime["Message-ID"] = msg_id
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(login_addr, pw)
            server.sendmail(from_addr or login_addr, [to], mime.as_string())
        return msg_id
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("SMTP send failed (%s via %s): %s", to, account, exc)
        return None


def verify(account: str = PERSONAL) -> dict:
    """Check whether ``account`` can ACTUALLY send right now — without sending.

    OAuth: a lightweight getProfile call. SMTP: a real login (no message). Returns
    {ok, method, address, reason} so the Connect page can show a true green/red,
    not just 'a key is saved'."""
    cfg = _account_cfg(account)
    # OAuth path first (matches send_message's preference).
    svc = _service(account)
    if svc is not None:
        try:
            prof = svc.users().getProfile(userId="me").execute()
            return {"ok": True, "method": "oauth",
                    "address": prof.get("emailAddress") or cfg.get("address"), "reason": None}
        except Exception as exc:  # pragma: no cover - network guard
            return {"ok": False, "method": "oauth", "address": cfg.get("address"),
                    "reason": f"OAuth token rejected ({str(exc)[:80]}) — reconnect."}
    # SMTP app-password path.
    login_addr, pw, from_addr, _reply = _smtp_login(account)
    if not (login_addr and pw):
        return {"ok": False, "method": None, "address": cfg.get("address"),
                "reason": "not connected — add an App Password or OAuth for this mailbox."}
    try:
        import smtplib
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.starttls()
            server.login(login_addr, pw)
        return {"ok": True, "method": "smtp", "address": from_addr or login_addr, "reason": None}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "method": "smtp", "address": from_addr or login_addr,
                "reason": f"SMTP login failed ({str(exc)[:80]}) — check the App Password."}


def _raw(account: str, to: str, subject: str, body: str) -> dict:
    mime = MIMEText(body, "html")
    mime["to"] = to
    mime["from"] = address_for(account)
    mime["subject"] = subject or "(no subject)"
    return {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}


def effective_account(account: str) -> str:
    """Resolve the mailbox that will actually send. Insurance runs primary-with-
    backup: if the primary insurance mailbox can't send but the backup can, use
    the backup. Every other account resolves to itself."""
    if account == INSURANCE and not is_configured(INSURANCE) and is_configured(INSURANCE_BACKUP):
        return INSURANCE_BACKUP
    return account


def send_message(to: str, subject: str, body: str, account: str = PERSONAL) -> str | None:
    """Send an email immediately from ``account``. Returns the message id or None.

    Uses the Gmail API when OAuth is configured; otherwise falls back to SMTP
    with an App Password (the simplest setup). Insurance falls back to its backup
    mailbox when the primary isn't configured.
    """
    if not to:
        return None
    account = effective_account(account)
    svc = _service(account)
    if svc is None:
        return _send_smtp(account, to, subject, body)  # App Password path
    try:
        sent = svc.users().messages().send(userId="me", body=_raw(account, to, subject, body)).execute()
        return sent.get("id")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Gmail send failed (%s via %s): %s", to, account, exc)
        return _send_smtp(account, to, subject, body)  # last-resort fallback


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
