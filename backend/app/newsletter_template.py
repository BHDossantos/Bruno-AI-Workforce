"""Newsletter HTML design — a real designed layout, not plain text.

Every newsletter issue gets a colored banner (with an optional photo per
business), a card-style content area with proper typography and spacing, and a
clear CTA button — instead of a bare paragraph. Falls back to a tasteful
CSS-only gradient banner when no photo is configured, so it never looks
unfinished even without an image.
"""
from __future__ import annotations

from .config import settings

# Per-funnel accent color + fallback banner gradient (CSS-only, no image needed).
_THEME = {
    "insurance": {"accent": "#6d28d9", "gradient": "linear-gradient(135deg,#6d28d9,#a78bfa)"},
    "bnbglobal": {"accent": "#0891b2", "gradient": "linear-gradient(135deg,#0891b2,#67e8f9)"},
    "savorymind": {"accent": "#ea580c", "gradient": "linear-gradient(135deg,#ea580c,#fb923c)"},
    "music": {"accent": "#db2777", "gradient": "linear-gradient(135deg,#db2777,#f472b6)"},
}
_BANNER_ATTR = {
    "insurance": "newsletter_banner_insurance", "bnbglobal": "newsletter_banner_bnb",
    "savorymind": "newsletter_banner_savorymind", "music": "newsletter_banner_music",
}


def banner_for(funnel: str) -> str:
    attr = _BANNER_ATTR.get(funnel, "")
    return (getattr(settings, attr, "") if attr else "") or ""


def _paragraphs(body: str) -> str:
    """Plain or lightly-formatted body text -> spaced HTML paragraphs."""
    parts = [p.strip() for p in (body or "").split("\n\n") if p.strip()]
    return "".join(f'<p style="margin:0 0 14px;line-height:1.6">{p}</p>' for p in parts) \
        or f'<p style="margin:0;line-height:1.6">{body or ""}</p>'


def render(*, funnel: str, label: str, subject: str, body: str,
          unsubscribe_url: str, cta_url: str | None = None,
          cta_label: str = "Get in touch") -> str:
    """A fully designed newsletter issue: banner (photo or gradient), card body,
    CTA button, and a compliant footer with a one-click unsubscribe link."""
    theme = _THEME.get(funnel, _THEME["insurance"])
    banner = banner_for(funnel)
    banner_html = (
        f'<img src="{banner}" alt="{label}" style="width:100%;max-height:220px;'
        f'object-fit:cover;display:block">'
        if banner else
        f'<div style="background:{theme["gradient"]};height:140px;display:flex;'
        f'align-items:center;justify-content:center">'
        f'<span style="color:#fff;font-size:22px;font-weight:700;'
        f'font-family:Georgia,serif;letter-spacing:.5px">{label}</span></div>'
    )
    cta_html = ""
    if cta_url:
        cta_html = (
            f'<div style="margin-top:22px;text-align:center">'
            f'<a href="{cta_url}" style="background:{theme["accent"]};color:#fff;'
            f'padding:12px 28px;border-radius:8px;text-decoration:none;'
            f'font-weight:600;display:inline-block">{cta_label}</a></div>'
        )
    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;
            background:#ffffff;border-radius:12px;overflow:hidden;
            border:1px solid #eee;box-shadow:0 2px 8px rgba(0,0,0,0.04)">
  {banner_html}
  <div style="padding:28px 26px">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;
                color:{theme["accent"]};font-weight:700;margin-bottom:6px">{label}</div>
    <h1 style="margin:0 0 16px;font-size:21px;color:#1a1a1a;font-family:Georgia,serif">{subject}</h1>
    <div style="font-size:15px;color:#333">{_paragraphs(body)}</div>
    {cta_html}
  </div>
  <div style="background:#fafafa;padding:16px 26px;font-size:11px;color:#999;
              border-top:1px solid #eee">
    You're receiving this because you reached out to {label}.
    <a href="{unsubscribe_url}" style="color:#999">Unsubscribe</a>
  </div>
</div>"""
