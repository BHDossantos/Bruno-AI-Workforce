"""Consistent HTML email template applied to every outbound email.

Wraps the AI-written body in a clean layout with the correct per-account
signature (so prospects can always call back) and a CAN-SPAM compliant footer
(sender identity, mailing address, unsubscribe line).
"""
from __future__ import annotations

from .config import settings


def _business(account: str) -> str:
    if account == "insurance":
        return settings.insurance_business_name or ""
    return settings.personal_business_name or ""


def _signature(account: str) -> str:
    """Per-account signature block with click-to-call phone numbers."""
    if account == "insurance":
        return (
            'Best regards,<br>'
            '<strong>Bruno Dossantos</strong><br>'
            'Phone: <a href="tel:+16175683000" style="color:#6d28d9;text-decoration:none">(617) 568-3000</a> ext. 119'
            ' &nbsp;|&nbsp; '
            'Cell: <a href="tel:+16039308272" style="color:#6d28d9;text-decoration:none">(603) 930-8272</a><br>'
            'Thrust Insurance — Independent Agent<br>'
            '<span style="color:#666">Languages: English, Portuguese, Spanish &amp; Italian</span>'
        )
    return (
        'Best regards,<br>'
        '<strong>Bruno Dos Santos, MBA, MSIT</strong> | IT &amp; Cloud Leader<br>'
        'Cell: <a href="tel:+16039308272" style="color:#6d28d9;text-decoration:none">(603) 930-8272</a>'
    )


def render(body: str | None, account: str = "personal") -> str | None:
    """Return the body wrapped in the standard HTML template."""
    if not body:
        return body

    # If the body is plain text, convert newlines to HTML breaks.
    html_body = body if "<" in body and ">" in body else body.replace("\n", "<br>")

    signature = _signature(account)
    business = _business(account)

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
