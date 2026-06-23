"""SMTP mailer used to deliver the CEO daily report."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings

log = logging.getLogger("bruno.mailer")


def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send an HTML email. Returns False (without raising) if SMTP isn't set up."""
    if not (settings.smtp_host and settings.report_from_email and to):
        log.info("SMTP not configured — report not emailed (subject=%s)", subject)
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.report_from_email
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.report_from_email, [to], msg.as_string())
        return True
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Failed to send report email: %s", exc)
        return False
