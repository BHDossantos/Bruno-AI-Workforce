"""Failure alerts — email the admin only when something needs attention.

Keeps involvement minimal: silent on success, a single email when a daily run
errors or a mailbox stops sending. No-ops gracefully when no mailbox is set up.
"""
from __future__ import annotations

import logging

from .config import settings
from .integrations import gmail

log = logging.getLogger("bruno.alerts")


def _recipient() -> str | None:
    return settings.report_to_email or settings.admin_email or None


def notify(subject: str, body_html: str) -> bool:
    """Send an alert email to the admin. Returns False if it couldn't send."""
    to = _recipient()
    if not to:
        return False
    account = "personal" if gmail.is_configured("personal") else "insurance"
    if not gmail.is_configured(account):
        log.warning("alert not sent (no mailbox configured): %s", subject)
        return False
    try:
        return bool(gmail.send_message(to, f"[Bruno AI] {subject}", body_html, account=account))
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("alert send failed: %s", exc)
        return False


def check_run(label: str, result: dict) -> None:
    """Scan an agent/commander run result for errors and alert if any are found."""
    errors = _collect_errors(result)
    if errors:
        rows = "".join(f"<li>{k}: {v}</li>" for k, v in errors.items())
        notify(f"{label} had {len(errors)} error(s)",
               f"The {label} run reported problems:<ul>{rows}</ul>"
               "Open the dashboard to review. (You only get this email when something fails.)")


def _collect_errors(obj, prefix: str = "") -> dict:
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        if "error" in obj and isinstance(obj["error"], str):
            out[prefix or "run"] = obj["error"]
        for k, v in obj.items():
            if k != "error":
                out.update(_collect_errors(v, f"{prefix}.{k}" if prefix else str(k)))
    return out
