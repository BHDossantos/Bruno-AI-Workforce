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
    """'phone# (978) 824-4228   Cell# 16039308272' — click-to-call, from config."""
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


# account → its newsletter/banner image setting (reused as the email header image).
_ACCOUNT_BANNER = {
    "insurance": "newsletter_banner_insurance",
    "bnb": "newsletter_banner_bnb",
    "savorymind": "newsletter_banner_savorymind",
}

# A one-line "here's what this is about" under the brand name, so every email
# states its purpose even before the body — this is a sales platform, not a memo.
_TAGLINE = {
    "insurance": "Licensed insurance — better coverage, often a lower rate.",
    "savorymind": "Fresh, chef-crafted meals your customers will love.",
    "bnb": "Consulting that ships results, not slide decks.",
}


def _header_image(account: str) -> str:
    """The header image URL for this email: the global email header image if set,
    else the account's banner image. Empty → the branded text bar is used instead."""
    attr = _ACCOUNT_BANNER.get(account or "")
    return ((settings.email_header_image or "").strip()
            or (getattr(settings, attr, "") if attr else "") or "").strip()


def _header(account: str, business: str) -> str:
    """A visual header on every email — the configured picture if there is one, else
    a branded color bar with the business name + a one-line purpose. Never blank,
    never a broken image."""
    brand = business or settings.sender_name or "Thrust Insurance"
    img = _header_image(account)
    if img:
        return (f'<img src="{img}" alt="{brand}" width="600" '
                f'style="width:100%;max-width:600px;display:block;border-radius:10px 10px 0 0">')
    tagline = _TAGLINE.get(account, "")
    sub = (f'<div style="font-size:13px;color:#ede9fe;margin-top:4px">{tagline}</div>'
           if tagline else "")
    return (f'<div style="background:#6d28d9;color:#fff;padding:18px 22px;'
            f'border-radius:10px 10px 0 0"><div style="font-size:20px;font-weight:700">'
            f'{brand}</div>{sub}</div>')


def render(body: str | None, account: str = "personal") -> str | None:
    """Return the body wrapped in the standard branded HTML email — header image (or
    branded bar), the message, an always-present call-to-action, signature + footer.
    A sales platform never sends a bare or blank message."""
    if not body:
        return body

    body = clean_body(body)
    # If the body is plain text, convert newlines to HTML breaks.
    html_body = body if "<" in body and ">" in body else body.replace("\n", "<br>")

    signature = _signature(account)
    business = _business(account)
    header = _header(account, business)

    # Always give the reader ONE clear action: book a time if a link is set, else
    # call/text the producer. A sales email with no next step is a wasted send.
    link = booking_link(account)
    btn = ('background:#6d28d9;color:#fff;padding:11px 20px;border-radius:8px;'
           'text-decoration:none;font-weight:600;display:inline-block')
    if link:
        cta = f'<a href="{link}" style="{btn}">Book a time</a>'
    else:
        tel = _tel(settings.producer_cell or settings.producer_office_phone or "")
        cta = (f'<a href="tel:{tel}" style="{btn}">Call or text me</a>' if tel
               else '<span style="font-weight:600;color:#6d28d9">Reply to this email to get started.</span>')
    cta_block = f'<div style="margin-top:18px">{cta}</div>'

    address = settings.company_address
    footer_bits = []
    if business or settings.sender_name:
        footer_bits.append(business or settings.sender_name)
    if address:
        footer_bits.append(address)
    footer_bits.append("If you'd prefer not to hear from us, reply with \"unsubscribe\" and we'll remove you.")
    footer = " &middot; ".join(footer_bits)

    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;line-height:1.5;max-width:600px;border:1px solid #ececec;border-radius:10px">
  {header}
  <div style="padding:20px 22px">
    <div>{html_body}</div>
    {cta_block}
    <div style="margin-top:18px">{signature}</div>
    <hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0">
    <div style="font-size:12px;color:#888">{footer}</div>
  </div>
</div>"""
