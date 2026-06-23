"""Centralised OpenAI prompt library for every agent.

Prompts are plain ``str.format`` templates so they stay readable and are easy
to tune. Each agent imports the templates it needs.
"""

# Candidate profile used by the Job Hunter for resume/cover-letter matching.
CANDIDATE_PROFILE = (
    "Senior engineering leader. Strengths: Site Reliability Engineering (SRE), "
    "cloud infrastructure (AWS/GCP/Azure), platform engineering, AI/data "
    "platforms, team leadership and scaling. Target titles: Director/Head of "
    "SRE, Director Cloud/Platform/Infrastructure Engineering, VP Engineering, "
    "Director AI Infrastructure, Director Data Platform, CTO / Fractional CTO."
)

# ── Agent 1: Executive Job Hunter ────────────────────────────────────────────
JOB_ARTIFACTS = """For the executive job below, write four artifacts for this candidate.

Candidate profile: {profile}

Job: {title} at {company} ({location})
Description: {description}

Return JSON with keys:
- "resume_match": 3 bullet points mapping the candidate's experience to the role's keywords.
- "cover_letter": a concise, confident cover letter (max 220 words).
- "recruiter_msg": a short LinkedIn message to a recruiter (max 90 words).
- "hiring_msg": a short direct message to the hiring manager (max 90 words).
"""

# ── Agent 2: Insurance Lead Generator ────────────────────────────────────────
INSURANCE_OUTREACH = """You are an insurance producer writing outreach for a prospect.

Prospect: {company_name} ({category}, {segment}) — {industry}, {city}
Why they may need insurance: {reason}

Return JSON with keys:
- "cold_email_subject": a short, compelling subject line.
- "cold_email_body": a compliant cold email body with a clear CTA and an unsubscribe line.
- "call_script": a 5-line phone opener.
- "linkedin_msg": a friendly LinkedIn connection message (max 80 words).
"""

# ── Agent 3: SavoryMind Growth ───────────────────────────────────────────────
MENU_ANALYSIS = """SavoryMind helps restaurants grow revenue with AI menu intelligence.
Analyze this restaurant for an outreach pitch.

Restaurant: {name} — {cuisine} in {city}. Website: {website}
Pain points (if any): {pain_points}

Return JSON with keys:
- "upsell": 3 concrete upsell opportunities.
- "menu_optimization": 3 menu optimization ideas.
- "pairing": 3 food/drink pairing ideas.
- "reputation_gaps": 2 likely review/reputation gaps to address.
"""

SAVORYMIND_PITCH = """Write personalized SavoryMind outreach to a restaurant.

Restaurant: {name} ({cuisine}, {city}). Owner/manager: {owner}
Key insight to lead with: {insight}

Return JSON with keys:
- "pitch_subject": a short, compelling subject line.
- "pitch_body": a warm, specific pitch email body (max 180 words) + unsubscribe line.
- "linkedin_msg": a short LinkedIn message (max 80 words).
- "demo_invite": a one-paragraph demo invitation.
"""

# ── Agent 4: Music Marketing ─────────────────────────────────────────────────
PLAYLIST_PITCH = """Write a playlist submission pitch for a Brazilian/Latin/romantic artist.

Playlist: {name} (genre: {genre}, curator: {curator})
Return JSON with keys:
- "pitch": a concise, respectful pitch (max 120 words) tailored to the playlist's genre.
"""

INFLUENCER_PITCH = """Write outreach to a music/culture influencer for an artist collaboration.

Influencer: {name} — {niche} on {platform} (@{handle})
Return JSON with keys:
- "dm_pitch": a short, genuine DM (max 70 words).
- "collab_pitch": a 2-sentence collaboration proposal.
"""

MUSIC_DAILY_CONTENT = """Create a daily music promotion content package for a Brazilian/Latin
romantic artist (samba, pagode, Brazilian jazz, R&B). Return JSON with keys:
- "reels": 3 short reel ideas.
- "captions": 3 captions.
- "hashtags": 10 hashtags.
- "story": 1 artist story post idea.
"""

# ── Agent 5: Instagram Growth ────────────────────────────────────────────────
INSTAGRAM_ENGAGEMENT = """Generate engagement suggestions for an Instagram target account.

Account: @{handle} in niche "{niche}", categorized as "{category}".
Return JSON with keys:
- "comment_idea": a thoughtful comment.
- "dm_opener": a non-salesy DM opener.
- "story_reply": a casual story reply.
"""

INSTAGRAM_CALENDAR = """Build a 7-day Instagram content calendar mixing these pillars:
gym, music, business, Rome, food, fatherhood, resilience.
Return JSON with key "calendar": a list of 7 objects {{"day", "pillar", "idea", "caption"}}.
"""

# ── Automated follow-ups ─────────────────────────────────────────────────────
FOLLOWUP_EMAIL = """Write follow-up email #{step} (of 7) to {name}, who has not replied yet.
Context of the original outreach: {context}

Keep it under 80 words, polite and value-add (don't be pushy), reference that you
reached out before, and end with a soft CTA plus a one-line unsubscribe note.
Return JSON with keys "subject" and "body".
"""

# ── Warm SMS (sent after a lead replies to our email) ────────────────────────
SMS_INTRO = """{name} just replied to our email about: {context}.
Write a short, warm SMS (max 300 chars) that continues the conversation naturally,
thanks them, and asks one easy question to move forward. Casual, human, no hard sell.
End with " Reply STOP to opt out." Return JSON with key "body".
"""

SMS_REPLY = """You are texting with {name} about: {context}.
Conversation so far (latest last):
{history}

Write the next SMS reply (max 300 chars), helpful and conversational, moving toward
a call or meeting. Return JSON with key "body".
"""

# ── Reply classification ─────────────────────────────────────────────────────
CLASSIFY_REPLY = """Classify this inbound reply from a prospect.

Reply: "{text}"

Return JSON with keys:
- "intent": one of "interested", "question", "objection", "not_interested", "unsubscribe", "neutral".
- "summary": a 1-line summary of what they want.
- "suggested_reply": a short suggested response (max 60 words).
"""

# ── Agent 6: CEO Dashboard ───────────────────────────────────────────────────
CEO_BRIEF = """You are the chief of staff producing a CEO daily executive brief.
Here is today's raw output from all agents (JSON):

{data}

Return JSON with keys:
- "summary": a 4-sentence executive summary.
- "top_actions": the 10 highest-ROI actions for today, each {{"action", "why", "area"}}.
- "urgent_follow_ups": list of urgent follow-ups due.
- "recommended_focus": one sentence on where to focus today.
"""
