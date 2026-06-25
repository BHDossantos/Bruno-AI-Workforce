"""The Bruno D brand bible — the single source of truth for the music universe.

We are not promoting songs. We are building a recognizable romantic-music brand:
"A man who believes real love still exists — and writes cinematic songs that make
people feel it." Every reel, caption, lyric video and sax solo should reinforce
the SAME identity, because a consistent identity is far harder to copy than any
single song and it's what gives artists long careers instead of one viral moment.

Everything here feeds the Content Factory's music prompts so output is always
on-brand, story-first, and pointed at streams + follows (never LinkedIn).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

# ── Identity ─────────────────────────────────────────────────────────────────
ARTIST = "Bruno D"
# Own a category instead of competing in a crowded one ("R&B").
CATEGORY = "Luxury Latin Soul"
IDENTITY = (
    "A man who believes real love still exists — and writes cinematic songs that "
    "make people feel it. Romantic storytelling over signature alto sax."
)
# The unfair advantage: a combination almost no other artist owns.
EDGE = (
    "Brazilian roots; lives between Italy and the U.S.; sings in English, Spanish "
    "& Portuguese; deep voice; alto sax as a signature instrument; executive/"
    "entrepreneur by day; jiu-jitsu athlete; real love stories set in Rome, Boston, "
    "Naples and Barcelona. Sound: luxury R&B + Pagode + Latin Soul — like Usher, "
    "Ne-Yo, Romeo Santos, Belo, Thiaguinho and Dilsinho, with saxophone."
)
SIGNATURE = "alto sax + deep voice + cinematic luxury romance (often violin too)"
# The cinematic places the story moves through.
CITIES = ["Rome", "Naples", "Barcelona", "Boston"]
# We sell feelings: every song should make someone say "I wish somebody loved me like that."
PROMISE = 'every piece should make someone feel "I wish somebody loved me like that."'

# Streaming/follow targets the brand should own (for playlist pitching + CTAs).
PLAYLIST_TARGETS = [
    "Romantic R&B", "Late Night Drive", "Date Night", "Wedding Songs",
    "Proposal Songs", "Heartbreak", "Pagode", "Latin Love", "Luxury Romance",
    "Study", "Relax", "Sleep",
]

# Default streaming links — editable in the Brand Profile. Goal of every post is
# to send the listener to ONE of these to stream/follow.
DEFAULT_LINKS = "Spotify: https://open.spotify.com/artist/1NoggpCXnG7WctASlZU1UG"

# Fan-facing, story-first content angles — this is the "universe," NOT music-
# industry thought leadership. These seed the Content Factory's "music" line.
CONTENT_ANGLES = [
    "the true story behind this lyric",
    "the girl who inspired this song",
    "a song I wrote walking through Rome",
    "sax-only version of the hook",
    "violin-only version of the hook",
    "studio at 2 AM building this song",
    "the one line everyone repeats from the new single",
    "what happened after that date in Naples",
    "how I wrote this chorus",
    "Barcelona sunset, a verse, and a saxophone",
    "the city that inspired this song",
    "acoustic / piano version of the hook",
    "a love letter set to music",
    "behind the song: who she was",
]

# The era arc — release as eras, not a stream of disconnected singles. Editable
# over time; surfaced so content can build anticipation around the current era.
ERAS = [
    "After The Storm", "Midnight Confessions", "Slowly Into Love",
    "Favorite Mistake", "Marry Me In This Lifetime",
]

# Channels the music brand lives on. LinkedIn is intentionally excluded — the
# user asked for NO music on LinkedIn, and it's the wrong room for romance anyway.
CHANNELS = ["instagram", "tiktok", "youtube", "facebook", "x"]


def links(db: Session) -> str:
    """Streaming/follow links from the Brand Profile, falling back to defaults."""
    from . import brand
    p = brand.get_profile(db)
    return (p.music_links or "").strip() or DEFAULT_LINKS


def genres(db: Session) -> str:
    from . import brand
    p = brand.get_profile(db)
    return (p.music_genres or "").strip() or f"{CATEGORY} — romantic R&B with alto sax"


def artist(db: Session) -> str:
    from . import brand
    p = brand.get_profile(db)
    return (p.music_artist or "").strip() or ARTIST


def cta(db: Session) -> str:
    """A single streaming call-to-action line for captions/scripts."""
    return f"Stream {artist(db)} — {links(db)}"


def promo_context(db: Session) -> str:
    """The brand brief injected into every music content prompt so the AI builds
    the universe (story + feeling + signature) and always drives streams/follows."""
    return (
        f"YOU ARE PROMOTING THE ARTIST '{artist(db)}' — build the BRAND, not a "
        f"generic music post. Do NOT talk about the music industry, marketing, or "
        f"'growth' in the abstract. Make a fan FEEL something and go press play.\n"
        f"- Category (own it): {CATEGORY}. Sound: {genres(db)}.\n"
        f"- Identity: {IDENTITY}\n"
        f"- Signature in every piece: {SIGNATURE}.\n"
        f"- The edge: {EDGE}\n"
        f"- Tell a real story — {PROMISE} Lean on the cities ({', '.join(CITIES)}), "
        f"the love stories, and the saxophone.\n"
        f"- TikTok/Reels: build around ONE repeatable line a listener wants to quote.\n"
        f"- YouTube: cinematic mini-movie energy (Italian streets, rooftops, rain, "
        f"black suit, sax), not a lecture.\n"
        f"- ALWAYS end with a clear call-to-action to stream/follow, using a link: "
        f"{links(db)}\n"
        f"- NEVER post this on LinkedIn."
    )
