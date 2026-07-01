"""Insurance carriers available in MA / NH / FL, for the CRM carrier dropdown.

A curated list of the major personal- and commercial-lines carriers writing in
Massachusetts, New Hampshire and Florida. The CRM accepts free text too, so an
unlisted carrier still saves — this just powers the dropdown / autocomplete.
"""
from __future__ import annotations

# National + strong-regional carriers active across MA/NH/FL.
CARRIERS: list[str] = [
    # National
    "Progressive", "GEICO", "State Farm", "Allstate", "Liberty Mutual",
    "Travelers", "Nationwide", "Farmers", "USAA", "American Family",
    "Erie", "Chubb", "The Hartford", "Kemper", "Mercury", "National General",
    "Encompass", "Foremost", "Bristol West",
    # Northeast (MA/NH) strong
    "Amica", "Plymouth Rock", "Safety Insurance", "Commerce (MAPFRE)", "Arbella",
    "Vermont Mutual", "The Hanover", "Quincy Mutual", "Norfolk & Dedham",
    "Concord Group", "Andover Companies (Merrimack Mutual)",
    # Florida-focused homeowners
    "Citizens Property Insurance", "Universal Property", "Tower Hill",
    "Florida Peninsula", "Heritage", "Kin", "Slide", "American Integrity",
    "Security First", "People's Trust",
    # Insurtech / life
    "Lemonade", "Hippo", "Branch", "Openly", "Banner Life", "Haven Life",
    "Prudential", "Northwestern Mutual", "MassMutual", "New York Life",
    "Lincoln Financial", "Corebridge (AIG Life)",
    "Other",
]

# Lines of business (matches the insurance_lines classifier).
LINES: list[str] = ["auto", "home", "life", "commercial"]
STATES: list[str] = ["MA", "NH", "FL"]
STATUSES: list[str] = ["Active", "Lapsed", "Renewed", "Cancelled"]
NOTE_KINDS: list[str] = ["note", "call", "email", "sms", "meeting"]
