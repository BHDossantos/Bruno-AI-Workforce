"""Daily LinkedIn founder post — brand awareness, not selling.

One post per day to LinkedIn for the BnB Global brand, but written as the FOUNDER's
personal thought-leadership, never a pitch. The goal is top-of-funnel: make people
curious about how the brand was built and want to learn from the person behind it —
so the network grows and brand awareness rises on its own. It deliberately does NOT
advertise services, quote prices, or push a call-to-action to buy.

Self-contained on purpose: the generic Content Factory produces sales-y content and
only auto-publishes in full-auto mode. This runs its own tight loop — one BnB founder
post/day, with an on-brand image, published straight to LinkedIn — so it works under
the lean insurance-only profile without turning the whole content machine (and its
cost) back on. No-ops cleanly when the AI or LinkedIn isn't connected.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import ContentItem

log = logging.getLogger("bruno.linkedin_founder")

_BUSINESS = "bnbglobal"
_CHANNEL = "linkedin"

# Curiosity-driven founder angles — journey, lessons, mindset. Never the product.
# Rotated by day so consecutive posts stay varied; the AI is also told what ran
# recently so it doesn't repeat a story.
_ANGLES = [
    "an early decision that felt reckless at the time but shaped everything",
    "a mistake that nearly ended it — and the lesson that came out of it",
    "the unglamorous daily habit that actually drove the growth",
    "a belief about building something that most people get backwards",
    "what you wish someone had told you on day one",
    "the moment you almost walked away, and the reason you didn't",
    "how you think about risk differently from most people",
    "the one skill that mattered far more than money or connections",
    "what building this taught you about people and trust",
    "a turning point most people never saw from the outside",
    "why you bet on something when everyone advised against it",
    "the difference between being busy and being effective, learned the hard way",
    "how you built a network starting from zero",
    "a principle you live by that quietly shaped the whole company",
    "what success actually looks like on an ordinary Tuesday",
    "the advice you'd give a younger founder who's afraid to start",
]

_SYSTEM = (
    "You are {name}, the founder of {brand}. You write a daily LinkedIn post in FIRST "
    "PERSON. This is personal thought leadership for brand awareness and networking — "
    "NOT marketing. Absolute rules: never sell, never pitch, never mention prices, "
    "services, offers, or 'DM me/book a call'. Do not advertise the company; instead "
    "make the reader curious about how you built it and want to learn from YOU. Tell a "
    "specific, honest, human story or lesson from your journey as an entrepreneur. "
    "Voice: confident, warm, plainspoken, a little contrarian; short punchy lines with "
    "line breaks (LinkedIn-native), 120-220 words, at most one tasteful emoji. End with "
    "an open question or an invitation to connect/follow and learn together — never a "
    "sales CTA. Output ONLY JSON."
)

_PROMPT = (
    "Write today's LinkedIn post. Angle: {angle}. "
    "Recent posts to NOT repeat (topics/openings): {recent}. "
    'Return JSON: {{"post": "the full LinkedIn post text with line breaks", '
    '"hashtags": "3-5 relevant hashtags like #Entrepreneurship #Founders", '
    '"image_prompt": "a short prompt for a clean, professional, on-brand photo that '
    "fits the post — no text in the image, no logos\"}}"
)


def _brand_name() -> str:
    return (settings.linkedin_founder_brand or "BnB Global").strip() or "BnB Global"


def _founder_name() -> str:
    return (settings.linkedin_founder_name or settings.producer_name or "").strip() or "the founder"


def _posted_today(db: Session) -> int:
    """BnB LinkedIn posts already PUBLISHED today — enforces the one-per-day cadence
    across retries / multiple ticks."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return int(db.query(func.count()).select_from(ContentItem).filter(
        ContentItem.business == _BUSINESS, ContentItem.channel == _CHANNEL,
        ContentItem.status == "published", ContentItem.published_at >= start).scalar() or 0)


def _recent_openings(db: Session, limit: int = 10) -> str:
    """First line of the last few posts, so the AI doesn't reopen with the same story."""
    rows = (db.query(ContentItem.body)
            .filter(ContentItem.business == _BUSINESS, ContentItem.channel == _CHANNEL)
            .order_by(ContentItem.created_at.desc()).limit(limit).all())
    firsts = [(b or "").strip().splitlines()[0][:80] for (b,) in rows if (b or "").strip()]
    return " | ".join(firsts) if firsts else "none yet"


def run(db: Session, *, force: bool = False) -> dict:
    """Generate + publish ONE BnB founder LinkedIn post for today (with an image),
    unless it's already been posted. ``force`` bypasses the once-a-day cap for a manual
    'Post now' test (the scheduler always calls with force=False). No-ops cleanly when
    unavailable."""
    from . import control, media
    from .ai import client
    from .integrations import linkedin_api

    if not settings.linkedin_founder_enabled:
        return {"skipped": "disabled (LINKEDIN_FOUNDER_ENABLED=false)"}
    if control.is_paused_safe(db):
        return {"skipped": "paused"}
    if not client.is_live():
        return {"skipped": "AI not connected"}
    if not linkedin_api.is_connected(db):
        return {"skipped": "LinkedIn not connected — authorize LinkedIn in Setup to auto-post."}
    if _posted_today(db) and not force:
        return {"skipped": "already posted today", "posted_today": 1}

    angle = _ANGLES[date.today().timetuple().tm_yday % len(_ANGLES)]
    system = _SYSTEM.format(name=_founder_name(), brand=_brand_name())
    try:
        data = client.complete_json(
            _PROMPT.format(angle=angle, recent=_recent_openings(db)), system=system)
    except Exception as exc:  # AI hiccup — try again next tick, don't crash the scheduler
        log.warning("linkedin founder post generation failed: %s", exc)
        return {"skipped": f"generation failed: {str(exc)[:120]}"}
    if not isinstance(data, dict):
        return {"skipped": "generation returned no post"}
    post = (data.get("post") or "").strip()
    if not post:
        return {"skipped": "empty post"}
    hashtags = (data.get("hashtags") or "").strip()

    # On-brand image so the post isn't bare text (LinkedIn favors posts with media).
    image_url = None
    if media.can_generate():
        img_prompt = (data.get("image_prompt") or f"clean professional photo about {angle}").strip()
        try:
            image_url = media.generate_and_host(img_prompt, f"linkedin-founder-{date.today().isoformat()}")
        except Exception:
            image_url = None  # image is best-effort; a strong text post still posts

    caption = f"{post}\n\n{hashtags}".strip()
    res = linkedin_api.post(db, caption, image_url)
    now = datetime.now(timezone.utc)
    db.add(ContentItem(
        topic=f"founder: {angle}", business=_BUSINESS, channel=_CHANNEL,
        title="Daily founder post", body=post, hashtags=hashtags,
        status="published" if res.get("ok") else "failed",
        meta={"angle": angle, "image_url": image_url, "result": res},
        scheduled_for=now, published_at=now if res.get("ok") else None))
    db.commit()
    if not res.get("ok"):
        log.warning("LinkedIn founder post did not publish: %s", res.get("reason"))
        return {"published": 0, "reason": res.get("reason"), "angle": angle}
    log.info("Published daily LinkedIn founder post (angle=%s, image=%s)", angle, bool(image_url))
    return {"published": 1, "angle": angle, "image": bool(image_url)}
