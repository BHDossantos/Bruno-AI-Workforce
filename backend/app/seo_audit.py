"""On-page SEO audit — fetch a URL, grade the fundamentals, list fixes.

A self-contained domain: ``audit`` fetches a page (``_fetch`` is the only network
seam, so tests stub it), extracts the on-page signals with the stdlib HTML parser
(no extra dependency), scores them 0-100 and returns ranked, human findings. This
is a fundamentals checker (title, meta, headings, alt text, canonical, content
depth, HTTPS) — not a crawler or a Lighthouse performance run. One new table.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from .models import SeoAudit

log = logging.getLogger("bruno.seo")

_TIMEOUT = 15.0
# Target ranges (chars) for the two text signals search engines truncate.
TITLE_MIN, TITLE_MAX = 30, 60
META_MIN, META_MAX = 70, 160
THIN_CONTENT = 300  # words


class _Extract(HTMLParser):
    """Pull the on-page signals in one pass. Stdlib only — tolerant of messy HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.meta_description: str | None = None
        self.meta_robots: str | None = None
        self.canonical: str | None = None
        self.h1: list[str] = []
        self.img_total = 0
        self.img_with_alt = 0
        self.links = 0
        self._in_title = False
        self._in_h1 = False
        self._skip_depth = 0           # inside <script>/<style>
        self._text_parts: list[str] = []
        self._h1_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = a.get("name", "").lower()
            if name == "description" and self.meta_description is None:
                self.meta_description = a.get("content", "").strip()
            elif name == "robots" and self.meta_robots is None:
                self.meta_robots = a.get("content", "").strip().lower()
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href", "").strip()
        elif tag == "h1":
            self._in_h1 = True
            self._h1_buf = []
        elif tag == "img":
            self.img_total += 1
            if a.get("alt", "").strip():
                self.img_with_alt += 1
        elif tag == "a" and a.get("href"):
            self.links += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
            text = " ".join(self._h1_buf).strip()
            if text:
                self.h1.append(text)

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title = ((self.title or "") + data).strip()
        if self._in_h1:
            self._h1_buf.append(data)
        s = data.strip()
        if s:
            self._text_parts.append(s)

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\b\w+\b", " ".join(self._text_parts)))


def _fetch(url: str) -> tuple[int | None, str, str | None]:
    """Fetch the page. Returns (status_code, html, error). The only network seam."""
    try:
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "BrunoSEOAudit/1.0"})
        return r.status_code, r.text, None
    except Exception as exc:
        return None, "", str(exc)[:200]


def _grade(score: int) -> str:
    return "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 \
        else "D" if score >= 60 else "F"


def _issue(severity: str, message: str) -> dict:
    return {"severity": severity, "message": message}


def analyze(url: str, status_code: int | None, html: str, error: str | None) -> dict:
    """Pure scoring over fetched content — no I/O, so it's trivially testable."""
    issues: list[dict] = []
    if error or status_code is None:
        return {"score": 0, "grade": "F", "status_code": status_code, "title": None,
                "meta_description": None, "h1_count": 0, "word_count": 0,
                "issues": [_issue("critical", f"Could not fetch the page: {error or 'no response'}")],
                "error": error or "no response"}
    if status_code >= 400:
        issues.append(_issue("critical", f"Page returned HTTP {status_code}"))

    e = _Extract()
    try:
        e.feed(html or "")
    except Exception:
        log.debug("HTML parse issue for %s", url, exc_info=True)

    score = 100

    # Title
    if not e.title:
        issues.append(_issue("critical", "Missing <title> tag")); score -= 20
    elif len(e.title) < TITLE_MIN:
        issues.append(_issue("warn", f"Title is short ({len(e.title)} chars; aim {TITLE_MIN}-{TITLE_MAX})")); score -= 6
    elif len(e.title) > TITLE_MAX:
        issues.append(_issue("warn", f"Title is long ({len(e.title)} chars; may be truncated in results)")); score -= 5

    # Meta description
    if not e.meta_description:
        issues.append(_issue("warn", "Missing meta description")); score -= 12
    elif len(e.meta_description) < META_MIN:
        issues.append(_issue("info", f"Meta description is short ({len(e.meta_description)} chars; aim {META_MIN}-{META_MAX})")); score -= 4
    elif len(e.meta_description) > META_MAX:
        issues.append(_issue("info", f"Meta description is long ({len(e.meta_description)} chars; may be truncated)")); score -= 3

    # Headings
    if len(e.h1) == 0:
        issues.append(_issue("warn", "No <h1> heading on the page")); score -= 10
    elif len(e.h1) > 1:
        issues.append(_issue("info", f"Multiple <h1> headings ({len(e.h1)}); use one primary heading")); score -= 4

    # Images / alt text
    missing_alt = e.img_total - e.img_with_alt
    if e.img_total and missing_alt:
        sev = "warn" if missing_alt > e.img_total / 2 else "info"
        issues.append(_issue(sev, f"{missing_alt} of {e.img_total} images missing alt text")); score -= min(10, missing_alt)

    # Canonical
    if not e.canonical:
        issues.append(_issue("info", "No canonical link — add rel=\"canonical\" to avoid duplicate-content splits")); score -= 4

    # Indexability
    if e.meta_robots and "noindex" in e.meta_robots:
        issues.append(_issue("critical", "Page is set to noindex — search engines will not index it")); score -= 25

    # Content depth
    if e.word_count < THIN_CONTENT:
        sev = "warn" if e.word_count < THIN_CONTENT / 2 else "info"
        issues.append(_issue(sev, f"Thin content ({e.word_count} words; aim {THIN_CONTENT}+ for ranking pages)")); score -= 8

    # HTTPS
    if urlparse(url).scheme != "https":
        issues.append(_issue("warn", "Page is not served over HTTPS")); score -= 8

    score = max(0, min(100, score))
    if not issues:
        issues.append(_issue("info", "No major on-page issues found — nice."))
    # Rank findings: critical → warn → info.
    order = {"critical": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: order.get(i["severity"], 3))
    return {"score": score, "grade": _grade(score), "status_code": status_code,
            "title": e.title, "meta_description": e.meta_description,
            "h1_count": len(e.h1), "word_count": e.word_count, "issues": issues, "error": None}


def audit(db: Session, *, url: str, business: str | None = None) -> SeoAudit:
    """Fetch + analyze + persist one audit."""
    if not urlparse(url).scheme:
        url = "https://" + url
    status_code, html, error = _fetch(url)
    result = analyze(url, status_code, html, error)
    row = SeoAudit(url=url, business=business, score=result["score"], grade=result["grade"],
                   status_code=result["status_code"], title=result["title"],
                   meta_description=result["meta_description"], h1_count=result["h1_count"],
                   word_count=result["word_count"], issues=result["issues"], error=result["error"])
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _to_dict(a: SeoAudit) -> dict:
    return {
        "id": str(a.id), "url": a.url, "business": a.business, "score": a.score,
        "grade": a.grade, "status_code": a.status_code, "title": a.title,
        "meta_description": a.meta_description, "h1_count": a.h1_count,
        "word_count": a.word_count, "issues": a.issues or [], "error": a.error,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def list_audits(db: Session, *, url: str | None = None, limit: int = 100) -> list[dict]:
    q = db.query(SeoAudit)
    if url:
        q = q.filter(SeoAudit.url == url)
    return [_to_dict(a) for a in q.order_by(SeoAudit.created_at.desc()).limit(limit).all()]


def get_audit(db: Session, audit_id) -> dict | None:
    a = db.get(SeoAudit, audit_id)
    return _to_dict(a) if a else None


def delete_audit(db: Session, audit_id) -> bool:
    a = db.get(SeoAudit, audit_id)
    if a is None:
        return False
    db.delete(a)
    db.commit()
    return True
