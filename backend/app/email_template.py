"""Consistent HTML email template applied to every outbound email.

Wraps the AI-written body in a clean layout with a signature and a CAN-SPAM
compliant footer (sender identity, mailing address, unsubscribe line). This runs
on top of the skill-based copy so every send looks templated and compliant.
"""
from __future__ import annotations

from .config import settings


def _business(account: str) -> str:
    if account == "insurance":
        return settings.insurance_business_name or ""
    return settings.personal_business_name or ""


def render(body: str | None, account: str = "personal") -> str | None:
    """Return the body wrapped in the standard HTML template."""
    if not body:
        return body

    # If the body is plain text, convert newlines to HTML breaks.
    html_body = body if "<" in body and ">" in body else body.replace("\n", "<br>")

    business = _business(account)
    signature_lines = [settings.sender_name]
    if business:
        signature_lines.append(business)
    signature = "<br>".join(line for line in signature_lines if line)

    # Optional booking-link call-to-action.
    cta = ""
    if settings.calendar_link:
        cta = (f'<div style="margin-top:16px">'
               f'<a href="{settings.calendar_link}" '
               f'style="background:#6d28d9;color:#fff;padding:10px 18px;border-radius:8px;'
               f'text-decoration:none;font-weight:600;display:inline-block">Book a time</a></div>')

    address = settings.company_address
    footer_bits = []
    if business or settings.sender_name:
        footer_bits.append(business or settings.sender_name)
    if address:
        footer_bits.append(address)
    footer_bits.append("If you'd prefer not to hear from us, reply with \"unsubscribe\" and we'll remove you.")
    footer = " &middot; ".join(footer_bits)

    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;line-height:1.5;max-width:600px">
  <div>{html_body}</div>
  {cta}
  <div style="margin-top:18px">{signature}</div>
  <hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0">
  <div style="font-size:12px;color:#888">{footer}</div>
</div>"""
