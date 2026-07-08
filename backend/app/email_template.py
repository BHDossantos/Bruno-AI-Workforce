"""Consistent HTML email template applied to every outbound email.

Wraps the AI-written body in a clean layout with the correct per-account
signature (so prospects can always call back) and a CAN-SPAM compliant footer
(sender identity, mailing address, unsubscribe line).
"""
from __future__ import annotations

import re

from .config import settings

# Cut an AI-added sign-off (and everything after it: "[Your Name]", P.S. lines)
# — the template appends the real signature, so the body must not carry one.
_SIGNOFF_RE = re.compile(
    r"\n\s*(best regards|best wishes|best|kind regards|warm regards|warmly|"
    r"sincerely|regards|thanks|thank you|cheers|talk soon|looking forward)\b.*",
    re.IGNORECASE | re.DOTALL,
)
# Leftover bracket placeholders the AI sometimes emits ("[Your Name]", "[Company]").
_PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,40}\]")


def clean_body(body: str | None) -> str | None:
    """Strip AI sign-offs/placeholders so only the template signature remains."""
    if not body:
        return body
    text = _SIGNOFF_RE.sub("", body)
    text = _PLACEHOLDER_RE.sub("", text)
    # Fix dangling greetings left by removed name placeholders ("Hi ,").
    text = re.sub(r"\b(Hi|Hello|Hey|Dear)\s*,", r"\1 there,", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# dispatch account → its per-business booking-link setting.
_ACCOUNT_CALENDAR = {
    "insurance": "calendar_link_insurance",
    "bnb": "calendar_link_bnb",
    "savorymind": "calendar_link_savorymind",
}


def booking_link(account: str | None) -> str:
    """The booking link for a business: its own if set, else the default link."""
    attr = _ACCOUNT_CALENDAR.get(account or "")
    return (getattr(settings, attr, "") if attr else "") or settings.calendar_link


def _business(account: str) -> str:
    if account == "insurance":
        return settings.insurance_business_name or ""
    return settings.personal_business_name or ""


def _tel(phone: str) -> str:
    """A US phone (formatted or raw) → an E.164 tel: href value."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        d = "1" + d
    return "+" + d if d else ""


def _phone_line() -> str:
    """'phone# (833) 854-7055   Cell# 16039308272' — click-to-call, from config."""
    parts = []
    if settings.producer_office_phone:
        parts.append(f'phone# <a href="tel:{_tel(settings.producer_office_phone)}" '
                     f'style="color:#6d28d9;text-decoration:none">{settings.producer_office_phone}</a>')
    if settings.producer_cell:
        parts.append(f'Cell# <a href="tel:{_tel(settings.producer_cell)}" '
                     f'style="color:#6d28d9;text-decoration:none">{settings.producer_cell}</a>')
    return " &nbsp;&nbsp; ".join(parts)


def _signature(account: str) -> str:
    """Per-account signature block with click-to-call phone numbers."""
    if account == "insurance":
        title = f" | {settings.producer_title}" if settings.producer_title else ""
        return (
            f'<strong>{settings.insurance_business_name or "Thrust Insurance"}</strong><br>'
            f'{settings.producer_name}{title}<br>'
            f'{_phone_line()}'
        )
    if account == "savorymind":
        return (
            '<strong>SavoryMind</strong> tastes better!<br>'
            f'{settings.producer_name} | <br>'
            f'{_phone_line()}'
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

    body = clean_body(body)
    # If the body is plain text, convert newlines to HTML breaks.
    html_body = body if "<" in body and ">" in body else body.replace("\n", "<br>")

    signature = _signature(account)
    business = _business(account)

    # Optional booking-link call-to-action (per-business, else default).
    cta = ""
    link = booking_link(account)
    if link:
        cta = (f'<div style="margin-top:16px">'
               f'<a href="{link}" '
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
