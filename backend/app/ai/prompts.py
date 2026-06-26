"""Centralised OpenAI prompt library for every agent.

Prompts are plain ``str.format`` templates so they stay readable and are easy
to tune. Each agent imports the templates it needs.
"""

# Candidate profile used by the Job Hunter for resume/cover-letter matching.
CANDIDATE_PROFILE = (
    "Bruno Dos Santos — Director-level SRE & Cloud Operations leader (Boston). "
    "10+ years leading multi-region AWS/GCP/Azure and hybrid environments. "
    "Highlights: raised uptime SLA from 98.5% to 99.95% with AWS EKS production "
    "clusters; led global SRE teams; cut cloud costs ~30% and deployment time "
    "~40%; built CI/CD with Terraform, Kubernetes/EKS, Jenkins/CloudBees and "
    "GitHub Actions; defined SLO/SLI frameworks and error budgets; observability "
    "with Grafana/Prometheus/Datadog. Recent roles: SRE Leader @ CVS Health; "
    "Head of DevOps & SRE @ SNHU; Director Cloud App Provisioning @ Deltek; "
    "Sr Manager Cloud Delivery @ UKG. MBA, IT Management. Fluent EN/PT/ES/IT. "
    "Target titles: Director/Head of SRE, Director Cloud/Platform/Infrastructure "
    "Engineering, VP Engineering, Director AI Infrastructure, Director Data "
    "Platform, CTO / Fractional CTO."
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
- "cold_email_subject": a short, compelling subject line (no placeholders).
- "cold_email_body": the email body ONLY. Address the business by its real name
  ({company_name}); never use placeholders like [Name] or [Your Name]. Open with
  a specific line, give one clear value point, end with a one-line CTA question.
  Do NOT add any greeting placeholder, sign-off, signature, or unsubscribe line —
  those are appended automatically. Keep it under 110 words.
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
- "pitch_subject": a short, compelling subject line (no placeholders).
- "pitch_body": the email body ONLY (max 150 words). Address the restaurant by
  its real name ({name}); never use placeholders like [Name] or [Your Name]. Do
  NOT add a greeting placeholder, sign-off, signature, or unsubscribe line — those
  are appended automatically.
- "linkedin_msg": a short LinkedIn message (max 80 words).
- "demo_invite": a one-paragraph demo invitation.
"""

# ── Agent 4: Music Marketing ─────────────────────────────────────────────────
PLAYLIST_PITCH = """Write a playlist submission pitch for Bruno D — a "Luxury Latin Soul"
artist: romantic R&B with a signature alto sax, deep voice, sung in English, Spanish &
Portuguese; cinematic love songs (think Usher/Ne-Yo meets Romeo Santos/Belo, with sax).

Playlist: {name} (genre: {genre}, curator: {curator})
{memory}
Return JSON with keys:
- "pitch": a concise, respectful pitch (max 120 words) tailored to the playlist's genre.
  Lead with the feeling/story and the saxophone signature; make the fit obvious.
  Use anything you remember about this curator (preferences, prior contact, timing)
  to personalize — never repeat a pitch they already declined.
"""

INFLUENCER_PITCH = """Write outreach to a music/culture influencer for an artist collaboration.

Influencer: {name} — {niche} on {platform} (@{handle})
{memory}
Return JSON with keys:
- "dm_pitch": a short, genuine DM (max 70 words).
- "collab_pitch": a 2-sentence collaboration proposal.
Use anything you remember about them to personalize; never repeat a prior pitch.
"""

MUSIC_DAILY_CONTENT = """Create a daily fan-facing content package that PROMOTES this
artist's music — the goal is to make people FEEL something and go stream/follow. Build
the brand (a romantic-music universe), not generic "music" posts. Never mention the music
industry, marketing, or growth in the abstract. This is NOT for LinkedIn.

{brand}
Artist: {artist}. Sound: {genres}.
{promo}

Return JSON with keys:
- "reels": 3 short reel ideas, each built around ONE repeatable line a listener would quote.
- "captions": 3 story-first captions, each ending with a stream/follow call-to-action + link.
- "hashtags": 10 hashtags (mix romance/R&B/Latin/sax + discovery tags).
- "story": 1 personal story post idea (the city, the love story, or the saxophone behind a song).
"""

MUSIC_RELEASE_KIT = """Turn ONE song into a complete release content kit for the artist.
The goal is an ERA, not a single post — every piece reinforces the same identity and
drives people to stream/follow. Story-first, cinematic, signature alto sax. NOT for LinkedIn.

{brand}
{promo}

SONG: "{title}"
Era: {era}. Story / inspiration: {story}. Setting/city: {city}. Language(s): {language}.

Return a JSON object. First, "key_line": the ONE short, repeatable lyric/line fans will
quote (the TikTok hook). Then one object per deliverable below, each with keys
"title", "body", and (for social pieces) "hashtags":
- "music_video": cinematic mini-movie treatment (scene-by-scene, the city, sax, wardrobe, mood).
- "lyric_video": concept + on-screen lyric styling notes.
- "behind_the_song": 45-60s script telling the true story behind the song.
- "sax_version": 20-30s reel script foregrounding the saxophone, + caption ending in a stream CTA.
- "acoustic_version": stripped reel concept + caption with CTA.
- "piano_version": piano reel concept + caption with CTA.
- "story_version": a personal caption telling who/what inspired it, ending in a stream CTA.
- "teaser": pre-release snippet idea that builds anticipation, + caption.
- "tiktok_hook": how to use the key_line as a trend (prompt for duets/uses), + caption.
- "reel_1", "reel_2", "reel_3": three distinct short reel cuts (different hook each), + caption + hashtags.
- "x_post": a punchy post under 280 chars with the key_line and a link CTA.
- "facebook_post": a warm, conversational post with a stream CTA.
Be specific and emotionally resonant; make a listener FEEL it and press play.
"""

# ── Agent 5: Instagram Growth ────────────────────────────────────────────────
INSTAGRAM_ENGAGEMENT = """Generate engagement suggestions for an Instagram target account,
on behalf of this brand:
{brand}

Target account: @{handle} in niche "{niche}", categorized as "{category}".
Return JSON with keys:
- "comment_idea": a thoughtful comment.
- "dm_opener": a non-salesy DM opener.
- "story_reply": a casual story reply.
"""

INSTAGRAM_CALENDAR = """Build a 7-day Instagram content calendar for THIS account/brand:
{brand}

Use the brand's own content pillars above (not generic ones). Make every idea and
caption specific to this business, its audience, and its voice.
Return JSON with key "calendar": a list of 7 objects {{"day", "pillar", "idea", "caption", "hashtags"}}.
"""

# ── Automated follow-ups ─────────────────────────────────────────────────────
FOLLOWUP_EMAIL = """Write follow-up email #{step} (of 7) to {name}, who has not replied yet.
Context of the original outreach: {context}
{memory}
Keep it under 80 words, polite and value-add (don't be pushy), reference that you
reached out before, and end with a soft CTA plus a one-line unsubscribe note.
Use anything you remember above to make it personal and well-timed — never repeat
yourself or contradict what you already know. Return JSON with keys "subject" and "body".
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


# ── Agent: BnB Global (tech consulting) ──────────────────────────────────────
CONSULTING_OUTREACH = """Write founder-led B2B outreach for B&B Global Services, a tech
consultancy ("From Idea to Operations"). Services: Strategy & fractional-CTO advisory,
Application & Product development, Data/Analytics/AI (GenAI, LLM apps, MLOps), Cloud/DevOps/
Platform engineering (AWS/Azure/GCP, IaC, Kubernetes, CI/CD), DevSecOps & Cybersecurity
(security assessments, IAM, vulnerability mgmt, compliance readiness), Reliability/SRE/BCDR
(observability, incident management, disaster recovery), and Managed IT (IMAC, service desk).

The founder's credibility (use briefly as proof, never exaggerate): {profile}

Prospect: {company_name} - {category} {industry} in {city}.

Pick the SINGLE most relevant, highest-ROI wedge for THIS prospect - e.g. cut cloud spend
20-40%, raise uptime/reliability and stop incidents, security/compliance (SOC 2) readiness,
ship a first production GenAI use case, or managed IT for a growing team. Lead with a specific
pain + measurable outcome, cite one proof point, close with a low-friction CTA: a free
20-minute assessment / "book a consultation". Concise, human, honest, CAN-SPAM compliant.

Return JSON with keys:
- "cold_email_subject": under 60 chars, specific, no clickbait.
- "cold_email_body": 90-140 words - one wedge, the outcome, one proof point, a soft CTA.
- "linkedin_msg": under 90 words, a warm connection note.
- "call_script": a 4-5 sentence phone opener.
"""


# ── Content Factory (one idea -> every channel) ──────────────────────────────
CONTENT_FACTORY = """You are the Creative Director of a one-person media company.
Turn ONE idea into channel-ready content for every platform, tailored to each
platform's format and audience. Business context / brand voice:
{brand}

Business line: {business}
Topic / idea: {topic}
{freshness}
{guidance}

Return a JSON object with these keys (omit none; keep each tight and high-quality):
- "angle": the specific angle/hook you chose (one sentence).
- "blog": {{"title": ..., "body": 500-800 word article in markdown}}.
- "linkedin": {{"body": 1300-char thought-leadership post, "hashtags": "#a #b #c"}}.
- "instagram": {{"title": reel hook, "body": 30-45s reel script, "caption": ..., "hashtags": ...}}.
- "tiktok": {{"title": hook, "body": 20-30s script, "hashtags": ...}}.
- "youtube": {{"title": Short title, "body": 45-60s script}}.
- "x": {{"body": a punchy post under 280 chars}}.
- "facebook": {{"body": a short conversational post}}.
- "email": {{"subject": ..., "body": a short newsletter section}}.
- "podcast": {{"body": a 5-bullet talking-point outline}}.
Be specific and useful; no filler, no false claims.
"""
