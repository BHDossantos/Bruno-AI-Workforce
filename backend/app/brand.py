"""Brand profile — the single source of truth that tailors every AI content
agent to the user's actual account/business. Seeded with sensible defaults on
first read; editable via the /profile API and the Settings page.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import BrandProfile

# Defaults so the app produces tailored-looking content before the user edits.
_DEFAULTS = dict(
    business_name="Bruno Dos Santos",
    niche="IT & cloud leadership; insurance (Thrust); SavoryMind restaurant growth; music",
    location="Boston / New Hampshire",
    audience="SMB owners, restaurants, hiring leaders, and music fans",
    value_prop="AI-driven marketing, sales outreach, and growth automation",
    website="",
    tone="warm, confident, concise, professional",
    instagram_handle="",
    content_pillars="behind-the-scenes, client wins, tips & how-tos, industry insight, social proof, offers",
    music_artist="Bruno Dos Santos",
    music_genres="Samba, Pagode, Brazilian jazz, Latin romance, R&B",
)


def get_profile(db: Session) -> BrandProfile:
    """Return the brand profile, creating it from defaults if it doesn't exist."""
    row = db.query(BrandProfile).first()
    if row is None:
        row = BrandProfile(**_DEFAULTS)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def context(db: Session) -> str:
    """A compact brand brief injected into content prompts so output is on-brand."""
    p = get_profile(db)
    bits = [
        f"Business: {p.business_name}" if p.business_name else "",
        f"Niche: {p.niche}" if p.niche else "",
        f"Location: {p.location}" if p.location else "",
        f"Target audience: {p.audience}" if p.audience else "",
        f"Offer / value prop: {p.value_prop}" if p.value_prop else "",
        f"Brand voice: {p.tone}" if p.tone else "",
        f"Instagram: @{p.instagram_handle.lstrip('@')}" if p.instagram_handle else "",
        f"Content pillars: {p.content_pillars}" if p.content_pillars else "",
    ]
    return "\n".join(b for b in bits if b)
