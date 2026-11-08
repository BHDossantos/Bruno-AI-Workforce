"""Strict Gmail transport for reviewed DOT outreach; no automatic caller is wired.

Reuse existing encrypted/runtime OAuth configuration. Never fall back to SMTP,
ESPs, another mailbox, or global BCC. The caller must durably reserve the send and
check suppression/consent/windows/caps before invoking send_reserved_once.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from hashlib import sha256
import json
import re

from email_validator import validate_email, EmailNotValidError
from . import gmail
from ..sender_signatures import Signature, compose


class VerificationError(ValueError):
    """Safe reason code only; never provider exception bodies or credentials."""


def address(value: str) -> str:
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise VerificationError("invalid_email_address") from exc


def fingerprint(sender: str, to: str, bcc: tuple[str, ...], subject: str, body: str, signature_digest: str | None = None) -> str:
    normalized_body = body.replace("\r\n", "\n").rstrip("\n")
    return sha256(json.dumps([address(sender), address(to), sorted({address(v) for v in bcc}),
                              subject, normalized_body, signature_digest], ensure_ascii=False).encode()).hexdigest()


def verified_service(expected_address: str):
    """Read-only live identity check using the configured personal OAuth account."""
    expected = address(expected_address)
    if address(gmail.address_for(gmail.PERSONAL)) != expected:
        raise VerificationError("configured_mailbox_mismatch")
    service = gmail._service(gmail.PERSONAL)
    if service is None:
        raise VerificationError("personal_gmail_oauth_unavailable")
    try:
        profile = service.users().getProfile(userId="me").execute(num_retries=0)
        actual = address(profile.get("emailAddress", ""))
    except Exception as exc:
        raise VerificationError("gmail_identity_check_failed") from exc
    if actual != expected:
        raise VerificationError("oauth_mailbox_mismatch")
    return service


def verify_mailbox(expected_address: str) -> dict:
    verified_service(expected_address)
    return {"verified": True, "address": address(expected_address), "provider": "gmail_oauth",
            "sending_enabled": False}


@dataclass(frozen=True)
class ReservedMail:
    """Server-side delivery contract, never deserialized directly from a request."""
    reservation_id: str
    sender: str
    to: str
    bcc: tuple[str, ...]
    subject: str
    body: str
    approved_fingerprint: str
    signature: Signature | None = None

    def raw(self, verified_bcc: tuple[str, ...]) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9-]{16,64}", self.reservation_id):
            raise VerificationError("invalid_reservation_id")
        if not self.subject.strip() or any(c in self.subject for c in "\r\n") or not self.body.strip():
            raise VerificationError("invalid_message_content")
        if len(self.bcc) > 2 or not {address(v) for v in self.bcc} <= {address(v) for v in verified_bcc}:
            raise VerificationError("bcc_not_verified")
        if fingerprint(self.sender, self.to, self.bcc, self.subject, self.body, self.signature.digest if self.signature else None) != self.approved_fingerprint:
            raise VerificationError("draft_changed_after_review")
        mime = compose(self.body, self.signature)
        mime["From"] = address(self.sender)
        mime["To"] = address(self.to)
        if self.bcc:
            mime["Bcc"] = ", ".join(sorted({address(v) for v in self.bcc}))
        mime["Subject"] = self.subject
        mime["Message-ID"] = f"<dot-{self.reservation_id}@workforce.invalid>"
        return {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}


@dataclass(frozen=True)
class SendResult:
    state: str  # not_attempted | accepted | unknown
    provider_id: str | None = None
    reason: str | None = None


def send_reserved_once(mail: ReservedMail, *, verified_bcc: tuple[str, ...],
                       dispatch_authorized: bool = False) -> SendResult:
    """One provider invocation, no retry. No app route/scheduler invokes this yet.

    The reservation must already be durable and exclusive across all senders.
    Timeout, missing result ID or exception after invocation stays unknown: never
    retry on that basis. Accepted means provider accepted, not delivered or sold.
    """
    if not dispatch_authorized:
        return SendResult("not_attempted", reason="dispatch_not_enabled")
    try:
        raw = mail.raw(verified_bcc)
        service = verified_service(mail.sender)
    except VerificationError as exc:
        return SendResult("not_attempted", reason=str(exc))
    except ValueError:
        return SendResult("not_attempted", reason="signature_validation_failed")
    try:
        result = service.users().messages().send(userId="me", body=raw).execute(num_retries=0)
        provider_id = result.get("id")
        return (SendResult("accepted", str(provider_id)) if provider_id
                else SendResult("unknown", reason="missing_provider_id"))
    except Exception:
        return SendResult("unknown", reason="provider_result_uncertain")


def verify_sent(mail: ReservedMail, provider_id: str) -> dict:
    """Read-only reconciliation; verifies exact sender/To/BCC/subject/plain body."""
    service = verified_service(mail.sender)
    try:
        message = service.users().messages().get(userId="me", id=provider_id, format="raw").execute(num_retries=0)
        if "SENT" not in message.get("labelIds", []):
            raise VerificationError("message_not_in_sent")
        parsed = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(message["raw"]))
        headers = lambda name: [v for _, v in getaddresses(parsed.get_all(name, []))]
        if len(headers("From")) != 1 or len(headers("To")) != 1 or headers("Cc"):
            raise VerificationError("recipient_headers_mismatch")
        plain = parsed.get_body(preferencelist=("plain",)) if parsed.is_multipart() else parsed
        if plain is None or plain.get_content_type() != "text/plain":
            raise VerificationError("plain_body_unavailable")
        content = plain.get_content().replace("\r\n", "\n").rstrip("\n")
        if mail.signature:
            suffix = "\n\n" + mail.signature.plain_text.replace("\r\n", "\n").rstrip("\n")
            if not content.endswith(suffix):
                raise VerificationError("signature_text_mismatch")
            content = content[:-len(suffix)]
            pngs = [part.get_payload(decode=True) for part in parsed.walk() if part.get_content_type() == "image/png"]
            if pngs != [mail.signature.png]:
                raise VerificationError("signature_asset_mismatch")
        expected_html = compose(mail.body, mail.signature).get_body(preferencelist=("html",))
        actual_html = parsed.get_body(preferencelist=("html",))
        normalize_html = lambda part: part.get_content().replace("\r\n", "\n").rstrip("\n") if part else None
        if normalize_html(expected_html) != normalize_html(actual_html):
            raise VerificationError("sent_html_mismatch")
        allowed_types = {"text/plain", "text/html", "image/png"} if mail.signature else {"text/plain"}
        if any(not part.is_multipart() and part.get_content_type() not in allowed_types for part in parsed.walk()):
            raise VerificationError("unexpected_attachment")
        actual = fingerprint(headers("From")[0], headers("To")[0], tuple(headers("Bcc")),
                             str(parsed.get("Subject", "")), content, mail.signature.digest if mail.signature else None)
        if actual != mail.approved_fingerprint:
            raise VerificationError("sent_content_mismatch")
        if parsed.get("Message-ID") != f"<dot-{mail.reservation_id}@workforce.invalid>":
            raise VerificationError("reservation_header_mismatch")
        return {"state": "sent_verified", "provider_id": provider_id, "delivery_confirmed": False}
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError("sent_verification_unavailable") from exc


def prior_sent(expected_address: str, recipient: str) -> dict:
    """Read-only, bounded duplicate check. Any match needs human reconciliation."""
    service = verified_service(expected_address)
    target = address(recipient)
    try:
        result = service.users().messages().list(userId="me", maxResults=100,
            q=f"in:sent {{to:{target} cc:{target} bcc:{target}}}").execute(num_retries=0)
        return {"message_ids": [m["id"] for m in result.get("messages", [])],
                "truncated": bool(result.get("nextPageToken")), "scope": "verified_personal_gmail_sent",
                "recipient": target, "mailbox": address(expected_address)}
    except Exception as exc:
        raise VerificationError("gmail_history_unavailable") from exc
