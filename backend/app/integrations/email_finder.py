"""Shared website → contact-email extractor used by all free lead sources.

Given a business website, fetches the homepage and a few common contact pages and
returns the first plausible contact email (preferring explicit ``mailto:`` links).
A per-run budget bounds how many sites we fetch so agent runs stay fast.
"""
from __future__ import annotations

import re

import httpx

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MAILTO_RE = re.compile(r"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.I)
_BAD = ("example.", "@2x", ".png", ".jpg", ".jpeg", ".gif", ".webp", "sentry", "wixpress",
        "your@", "email@", "domain.com", "@sentry", "godaddy", "u003e", "@example",
        "name@", "test@test")
_PATHS = ("", "/contact", "/about")
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BrunoAI/1.0; +https://example.com/bot)"}
_TIMEOUT = httpx.Timeout(5.0, connect=4.0)


def clean_email(e: str | None) -> str | None:
    if not e:
        return None
    e = e.strip().lower().strip(".,;:)(<>\"'")
    if "@" not in e or e.count("@") != 1 or any(b in e for b in _BAD):
        return None
    domain = e.split("@")[-1]
    return e if "." in domain else None


def extract_email(url: str | None, budget: list[int]) -> str | None:
    """Return a contact email from the site, or None. ``budget`` is a 1-item list
    holding the remaining fetch allowance (mutated in place)."""
    if not url or budget[0] <= 0:
        return None
    if not url.startswith("http"):
        url = "https://" + url
    budget[0] -= 1
    base = url.rstrip("/")
    for path in _PATHS:
        try:
            r = httpx.get(base + path, timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS)
            html = r.text
            for m in _MAILTO_RE.findall(html):   # explicit mailto links first
                e = clean_email(m)
                if e:
                    return e
            for m in _EMAIL_RE.findall(html):     # then any address in the page
                e = clean_email(m)
                if e:
                    return e
        except Exception:
            continue
    return None
