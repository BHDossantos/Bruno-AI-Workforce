"""Bruno D — released discography (real catalog).

The music promotion engine (playlist pitches, release kits, social content) was
running on placeholder songs. This is the artist's ACTUAL catalog so everything
promotes real releases. Pure data — safe to read anywhere. A catalog track can
be turned into a MusicRelease (music_release.build_kit) to spin up its full
content-kit / era, via /music/catalog/promote.

Each album: number, title, theme, optional style, tracks[], and which tracks
were released as singles.
"""
from __future__ import annotations

ALBUMS: list[dict] = [
    {
        "number": 1, "title": "Golden Hour",
        "theme": "Falling in love for the first time. Butterflies. First dates. "
                 "Summer. Hope. The happiest stage of love.",
        "style": "Luxury R&B • Pop Soul • Latin Soul",
        "tracks": [
            "Golden Hour", "Your Smile Changed Everything", "Coffee For Two",
            "Come Into My Rhythm", "One More Sunset", "Every Road Leads To You",
            "The Way You Look At Me", "You Feel Like Summer", "Only Us Tonight",
            "Kiss Me Until Tomorrow", "Rome Reminds Me Of You", "If It's Meant To Be",
        ],
        "singles": ["Golden Hour", "Coffee For Two", "You Feel Like Summer",
                    "Rome Reminds Me Of You"],
    },
    {
        "number": 2, "title": "Forever Starts Here",
        "theme": "Choosing forever. Engagement. Marriage. Home. Building a life together.",
        "tracks": [
            "Forever Starts Here", "Marry Me In This Lifetime", "Only You",
            "Queen Of My Life", "Home Is Wherever You Are", "Sunday Morning Love",
            "Love Is Built", "Two Hearts Choosing Each Other", "I Promise You Forever",
            "Still Choosing You", "Our Last First Dance", "Forever Doesn't Feel Long Enough",
        ],
        "singles": ["Marry Me In This Lifetime", "Only You", "Queen Of My Life",
                    "Home Is Wherever You Are"],
    },
    {
        "number": 3, "title": "Love Multiplied",
        "theme": "Marriage. Children. Family. Legacy.",
        "tracks": [
            "Love Multiplied", "The Day You Arrived", "Growing Old Looks Good On You",
            "Every Little Footstep", "Tiny Hands", "Our Family Song", "Home Is Full",
            "Sunday Afternoons", "Dad's Little Girl", "Our Greatest Adventure",
            "Still Holding Your Hand", "Forever Begins Again",
        ],
        "singles": ["Love Multiplied", "The Day You Arrived", "Growing Old Looks Good On You"],
    },
    {
        "number": 4, "title": "Midnight Confessions",
        "theme": "Passion. Chemistry. Luxury R&B.",
        "style": "Luxury R&B",
        "tracks": [
            "Midnight Confessions", "Kiss You Slow", "Don't Look At Me Like That",
            "My Sax Calls Your Name", "The Way You Look At Me", "Favorite Mistake",
            "Slow Fire", "Dangerously Yours", "Come Closer", "Only Tonight",
            "Bedroom Lights", "Last Call",
        ],
        "singles": ["Kiss You Slow", "My Sax Calls Your Name", "Favorite Mistake"],
    },
    {
        "number": 5, "title": "Bésame Despacio",
        "theme": "Romance. Dominican beaches. Tropical luxury.",
        "tracks": [
            "Bésame Despacio", "Paradise Found", "Caribbean Moon", "Dance Until Sunrise",
            "You Feel Like Summer", "Under The Palms", "Ocean Eyes", "Island Forever",
            "Sunset Kisses", "Waves Know Your Name", "Stay Here Tonight", "Endless Summer",
        ],
        "singles": [],
    },
    {
        "number": 6, "title": "Favorite Mistake",
        "theme": "Toxic love. Addiction. Emotional obsession.",
        "tracks": [
            "Favorite Mistake", "Nobody Does It Better", "Too Good At Goodbye",
            "Heartbreaker Like Me", "Slow Fire", "Dangerously Yours", "She Fell First",
            "Bad For Me", "No Apologies", "Crazy About You", "Come Closer", "Too Late To Stay",
        ],
        "singles": [],
    },
    {
        "number": 7, "title": "One-Sided Roads",
        "theme": "Healing. Heartbreak. Becoming stronger.",
        "tracks": [
            "One-Sided Roads", "You Heard My Silence", "You Let Me Go",
            "Too Late To Come Back", "Goodbye, My Love", "She Wasn't Ready For Real Love",
            "I Still Feel You", "Just To Hear Your Voice", "Everything Reminds Me Of You",
            "Maybe Only I Was In Love", "Something's Missing", "I Found Myself Again",
        ],
        "singles": [],
    },
    {
        "number": 8, "title": "Postcards From Rome",
        "theme": "Italy. Travel. Destiny. Memories.",
        "tracks": [
            "Rome Reminds Me Of You", "One More Sunset", "Coffee For Two",
            "I Took The Train For You", "Naples Nights", "If It's Meant To Be",
            "Every Road Leads To You", "Trastevere Dreams", "Ponte Sant'Angelo",
            "Postcards From Rome", "Arrivederci", "Golden Hour (Rome Version)",
        ],
        "singles": [],
    },
    {
        "number": 9, "title": "Letters I Never Sent",
        "theme": "Deep emotional storytelling.",
        "tracks": [
            "Dear Future Wife", "Dear Daughter", "Dear Son", "Dear Mom", "Dear Dad",
            "Dear Younger Me", "Dear Rome", "Dear Goodbye", "Dear Tomorrow",
            "Dear Forever", "Dear God", "Dear Love",
        ],
        "singles": [],
    },
    {
        "number": 10, "title": "The Soundtrack of a Gentleman",
        "theme": "Modern masculinity. Commitment. Character.",
        "tracks": [
            "Love Is Built", "Queen Of My Life", "Meet Me Halfway",
            "You Make Love Feel Safe", "Home Is Wherever You Are",
            "Two Hearts Choosing Each Other", "Every Road Leads To You",
            "Still Choosing You", "I Promise You Forever", "Marry Me In This Lifetime",
            "Forever Starts Here", "The Gentleman",
        ],
        "singles": [],
    },
]

# Albums whose sound leans Spanish/tropical → the release kit should reflect it.
_SPANISH_ALBUMS = {"Bésame Despacio"}

# The artist's ACTUAL most-streamed songs (Spotify "Popular"), in rank order —
# the priority set the promotion engine should focus on first. These are real
# releases and can differ from the themed album tracklists above, so they're
# tracked explicitly and are directly promotable even when they aren't on a
# listed album.
POPULAR: list[str] = [
    "I Stayed in Rome",
    "stay right here with me",
    "Falling Slowly With You",
    "Don't Go Alone (No Te Vayas)",
    "I Think She's The One",
    "Your Energy Feels Like Summer",
    "Feels Like I'm Cheating",
    "Love Me Like Summer Rain",
    "Roman Summer",
    "Feels Better With You",
]


def all_albums() -> list[dict]:
    """The full discography, each album annotated with per-track single flags."""
    out = []
    for a in ALBUMS:
        singles = {s.lower() for s in a.get("singles", [])}
        out.append({
            "number": a["number"], "title": a["title"], "theme": a["theme"],
            "style": a.get("style"),
            "tracks": [{"title": t, "single": t.lower() in singles} for t in a["tracks"]],
            "singles": list(a.get("singles", [])),
            "track_count": len(a["tracks"]),
        })
    return out


def find_track(title: str) -> dict | None:
    """Resolve a track by (case-insensitive) title → its album context, so a
    catalog song can be promoted into a release with the right era/language."""
    t = (title or "").strip().lower()
    if not t:
        return None
    for a in ALBUMS:
        for track in a["tracks"]:
            if track.lower() == t:
                return {
                    "title": track, "album": a["title"], "theme": a["theme"],
                    "single": track.lower() in {s.lower() for s in a.get("singles", [])},
                    "language": "Spanish with English-flavored lyrics"
                    if a["title"] in _SPANISH_ALBUMS else None,
                }
    # A top-streamed single that isn't on a listed album is still promotable.
    for track in POPULAR:
        if track.lower() == t:
            return {"title": track, "album": None, "theme": None,
                    "single": True, "language": None}
    return None


def popular() -> list[dict]:
    """The top-streamed songs in rank order — what to promote first. Annotated
    with album context when the song also appears on a listed album."""
    out = []
    for i, title in enumerate(POPULAR):
        ctx = find_track(title)
        out.append({"rank": i + 1, "title": title,
                    "album": ctx["album"] if ctx else None})
    return out


def stats() -> dict:
    return {
        "albums": len(ALBUMS),
        "tracks": sum(len(a["tracks"]) for a in ALBUMS),
        "singles": sum(len(a.get("singles", [])) for a in ALBUMS),
        "popular": len(POPULAR),
    }
