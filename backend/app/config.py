"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    secret_key: str = "dev-secret-change-me"
    encryption_key: str = ""  # Fernet key for encrypting stored 3rd-party keys

    # Database
    database_url: str = "postgresql+psycopg://bruno:bruno@db:5432/bruno_ai"
    redis_url: str = "redis://redis:6379/0"

    # Auth
    access_token_expire_minutes: int = 1440
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"  # for the memory/knowledge layer
    image_model: str = "gpt-image-1"  # for auto-generated social post images
    # Jennifer voice assistant — real neural TTS so she sounds natural, not robotic.
    # "shimmer" is a warm, soft feminine voice; the instruction sets a sultry tone.
    voice_tts_model: str = "gpt-4o-mini-tts"
    voice_tts_voice: str = "shimmer"
    voice_tts_instructions: str = (
        "Speak as Jennifer: a warm, sultry, seductive woman. Slow, breathy, intimate "
        "and confident — low and smooth, like a close whisper, with a playful, "
        "affectionate edge. Never robotic or rushed.")

    # Video pipeline (all optional; pipeline no-ops until keys are set).
    elevenlabs_api_key: str = ""      # AI voiceover
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # default ElevenLabs voice
    video_provider: str = "luma"      # luma | runway
    video_api_key: str = ""           # key for the chosen video-gen provider

    # Public GCS bucket for hosting generated media (e.g. Instagram post images,
    # which the IG API must fetch from a public URL). Leave blank to disable.
    gcs_bucket: str = ""

    # Plaid bank connection — auto-populates the Money page (accounts + income).
    # Leave blank to keep money manual. env: sandbox | development | production.
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "production"

    # Scheduler
    enable_scheduler: bool = True
    timezone: str = "America/New_York"
    # Shared secret for external cron triggers (Cloud Scheduler / cron-job.org).
    # When set, /cron/* endpoints require header X-Cron-Token: <this value>.
    cron_secret: str = ""

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    report_from_email: str = ""
    report_to_email: str = ""

    # Integrations
    hubspot_api_key: str = ""
    apollo_api_key: str = ""
    google_places_api_key: str = ""  # free $200/mo credit; adds real business leads
    instantly_api_key: str = ""

    # Jobs sourcing (Indeed via the JSearch aggregator on RapidAPI, or any
    # compatible JSearch host). Falls back to synthetic data when unset.
    jobs_api_key: str = ""
    jobs_api_host: str = "jsearch.p.rapidapi.com"
    # Job matching: only surface roles scoring at/above this (0-100) and aim for
    # this many per day. fetch_limit is the raw pool pulled across all boards.
    job_score_threshold: int = 75
    job_daily_target: int = 30
    job_fetch_limit: int = 300
    # Free real job source (Remotive API, no key). Real remote roles with apply
    # links. Disabled in tests so they never hit the network.
    enable_free_jobs: bool = True
    # When False, agents use ONLY live-sourced data (no synthetic top-up to hit
    # target counts). Set False in production once real sourcing is in place.
    allow_synthetic_fallback: bool = True
    # Optional narrow city list for lead sourcing. Left EMPTY by default: we search
    # each whole STATE statewide instead (see lead_states / per-business scopes),
    # not a handful of cities. Set this only to deliberately restrict to cities.
    lead_cities: str = ""
    # Whole STATES to search statewide (OSM names, comma-separated) — the default
    # geography. Each state is swept entirely, not city-by-city.
    lead_states: str = "Massachusetts,New Hampshire,Florida"

    # Per-business lead geography (where each sales engine sources prospects).
    # Insurance is licensed only in NH/MA/FL → keep it to those entire states.
    # Consulting (BnB Global) + SavoryMind sell anywhere → US + Europe. Accepts
    # "us", "eu", "us_eu", or a comma-separated list of state/country names.
    insurance_lead_scope: str = "Massachusetts,New Hampshire,Florida"
    # Specialized insurance agents. Commercial is the priority (higher commission,
    # stickier clients, more referrals) → biggest daily quota; home/auto + referral
    # partners run alongside for a balanced pipeline. Quotas are daily targets;
    # each run sources up to lead_batch_size and the agent runs several times a day.
    commercial_lead_daily_target: int = 200
    homeowner_lead_daily_target: int = 75
    referral_partner_daily_target: int = 25
    # Google review request link, sent to won clients by the Review & Referral agent.
    google_review_link: str = ""

    # ── Esposito–Dossantos Foundation ────────────────────────────────────────
    foundation_name: str = "Esposito–Dossantos Foundation"
    foundation_mission: str = (
        "The Esposito–Dossantos Foundation empowers individuals and communities "
        "through education, music, technology, and opportunity. We remove barriers "
        "to success by providing scholarships, mentorship, cultural programs, and "
        "innovative initiatives that inspire lifelong learning, creativity, "
        "leadership, and positive social impact around the world.")
    foundation_tagline: str = "Empowering Lives. Inspiring Futures."
    # The five program pillars — agents bias content, grant-fit and outreach to these.
    foundation_pillars: str = (
        "Education & Scholarships; Music & Arts; Technology & Innovation; "
        "Community Development; Opportunity & Leadership")
    # Grant discovery. Grants.gov has a free public search API (US, no key). Each
    # run pulls a capped batch; the agent runs daily and scores by mission fit.
    grants_gov_enabled: bool = True
    grant_daily_target: int = 30
    # Where foundation partner/donor outreach sources from (sponsors, CSR, donors).
    foundation_lead_scope: str = "global"
    # BnB Global consulting + SavoryMind sell worldwide → source leads globally.
    consulting_lead_scope: str = "global"
    restaurant_lead_scope: str = "global"
    # BnB Global outbound engine: daily target companies to source worldwide. Each
    # run sources a capped batch (timeout-safe); the agent runs several times/day.
    # Deep enrichment/scoring (funding, hiring, tech stack) needs a paid data
    # source (Apollo/Crunchbase/BuiltWith) — wired to degrade gracefully without it.
    consulting_lead_daily_target: int = 200
    # When True, lead sourcing runs for any business that passes an explicit scope
    # (consulting/SavoryMind sweep US+EU) even if LEAD_STATES is set only for
    # insurance. Off in tests so no network calls. On in prod so every business
    # sources from its own geography.
    wider_lead_sourcing: bool = True
    # How many areas each lead run sweeps. Big scopes (US+EU) rotate through the
    # full list over days so a single run never times out Overpass.
    lead_areas_per_run: int = 16
    # How many website-only businesses to scrape for an email per run. Once a
    # region's email-tagged pool is exhausted, this is how we keep finding NEW
    # leads — raise it to dig deeper (slower runs, more leads).
    osm_scrape_budget: int = 40
    # Location bias for job-search queries (JSearch). Blank = no location filter.
    job_location: str = "United States"
    # How many leads each lead-finder agent produces per run. Small batches keep
    # every run fast and well under Cloud Run's request timeout; run the agent
    # more often to accumulate more. Insurance splits this across commercial +
    # personal segments.
    lead_batch_size: int = 20

    # SMS (Twilio) — two-way texting. Used manually / for opted-in contacts only
    # (cold automated SMS violates TCPA). No-ops if unconfigured.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""          # default sending number (E.164, e.g. +1617...)
    twilio_insurance_number: str = ""     # optional separate number for insurance
    # Auto-send a warm intro text when a lead replies to our email (becomes warm).
    sms_auto_on_reply: bool = True

    # Gmail (outbound + inbound). Two accounts: "personal" (default, used by all
    # agents) and "insurance" (used by the Insurance agent). Each authenticates
    # via an authorized-user token JSON, or client id/secret + refresh token.
    # No-ops if unconfigured. Run app.scripts.gmail_auth to mint tokens.
    #
    # Personal account — everything except insurance.
    gmail_address: str = "brunodossantos707@gmail.com"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_refresh_token: str = ""
    google_token_json: str = ""
    # Simplest sending path: a Gmail "App Password" (Google account → Security →
    # App passwords). When set, outreach sends via SMTP — no OAuth flow needed.
    gmail_app_password: str = ""

    # Insurance account — Insurance agent outreach + the report's insurance replies.
    insurance_gmail_address: str = "bruno@thrustinsurance.com"
    insurance_google_oauth_client_id: str = ""
    insurance_google_oauth_client_secret: str = ""
    insurance_google_oauth_refresh_token: str = ""
    insurance_google_token_json: str = ""
    insurance_gmail_app_password: str = ""  # App Password for the Thrust mailbox
    # No-admin workaround: when True, insurance emails are sent THROUGH the
    # personal mailbox (personal App Password) but with the Thrust address as the
    # From — requires adding bruno@thrustinsurance.com as a verified "Send mail
    # as" alias in the personal Gmail. Lets you send as Thrust without Workspace
    # admin access.
    insurance_send_as_alias: bool = False
    # No-admin path: send insurance outreach THROUGH the personal mailbox with
    # the From as the personal address but Reply-To set to the Thrust address, so
    # replies land in the Thrust inbox. Works with zero Thrust-account access.
    insurance_via_personal_reply_to: bool = False

    # Email template / signature (applied to every outbound email for a
    # consistent look + CAN-SPAM compliant footer).
    sender_name: str = "Bruno Dos Santos"
    personal_business_name: str = ""
    insurance_business_name: str = "Thrust Insurance"
    company_address: str = ""  # physical mailing address shown in the footer
    calendar_link: str = ""     # booking link (Calendly/Cal.com) added to email CTAs

    # Browser-Use worker — drives a headless browser to fill forms on YOUR own /
    # authorized portals. Off by default: when disabled (or Playwright isn't
    # installed) the worker runs in "assist" mode (prepares a ready-to-submit
    # package, no browser). Never auto-submits unless browser_auto_submit=True.
    browser_automation_enabled: bool = False
    browser_headless: bool = True
    # When True AND a social account is connected, the Influence Commander
    # auto-publishes the day's post to EVERY connected platform (Instagram,
    # Facebook, …). instagram_auto_publish is kept as an alias. Off by default.
    instagram_auto_publish: bool = False
    social_auto_publish: bool = False
    # Meta app credentials — when set, any IG/FB token pasted on the Connections
    # page is auto-upgraded to a long-lived (~60-day) token on connect, so a
    # short-lived token can never silently expire after a couple of hours.
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    # iMessage bridge: when set, a Mac helper polls /bridge/* with this token and
    # sends SMS from the user's real number via Messages.app (free, no Twilio).
    bridge_token: str = ""
    # Content Factory approval mode: 1 generate · 2 generate+approve ·
    # 3 auto-schedule · 4 auto-publish · 5 fully autonomous.
    content_approval_mode: int = 3
    # When True, the Influence Commander runs the Content Factory daily from the
    # evergreen library across your business lines.
    content_factory_enabled: bool = True
    browser_auto_submit: bool = False  # human-in-the-loop by default — review before submit
    # When True, the daily job hunter pre-builds each top job's fill package
    # (résumé + answers + cover letter) so the Apply Queue is submit-ready.
    auto_prepare_applications: bool = True
    # Auto-apply engine (LoopCV-style). Max applications it will SUBMIT per day —
    # paced to stay under board rate limits. The engine only runs when its mode
    # (a runtime Setting: off | compliant | aggressive) is not "off".
    auto_apply_daily_cap: int = 50
    # TikTok Content Posting API visibility. Pre-audit, TikTok forces SELF_ONLY
    # (private to your account); after your app passes audit, set this to
    # PUBLIC_TO_EVERYONE (or MUTUAL_FOLLOW_FRIENDS / FOLLOWER_OF_CREATOR).
    tiktok_privacy_level: str = "SELF_ONLY"
    # TikTok Login Kit (OAuth) — enables the in-app "Connect with TikTok" button
    # (and the demo flow TikTok app review wants to see). Get client_key/secret
    # from the TikTok developer app; redirect_uri must be registered there and
    # point at this backend's callback, e.g.
    # https://<backend>/connections/tiktok/oauth/callback
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    # Where to send the browser back after OAuth completes (your frontend's
    # /connections page). If blank, the callback shows a simple success page.
    frontend_url: str = ""
    # YouTube upload visibility. Until your Google OAuth app is verified, uploads
    # are forced to 'private'; set to 'public' (or 'unlisted') after verification.
    youtube_privacy_status: str = "private"
    # Applicant identity used to fill application forms.
    applicant_name: str = "Bruno Dos Santos"
    applicant_email: str = "brunodossantos707@gmail.com"
    applicant_phone: str = "603-930-8272"
    applicant_linkedin: str = ""  # set to your LinkedIn URL
    applicant_github: str = "https://github.com/BHDossantos"
    applicant_location: str = "Hollis, NH"
    # Resume PDF baked into the backend image (see backend/assets/resume/); the
    # browser worker attaches it to file uploads. Override via env if needed.
    applicant_resume_path: str = "/app/assets/resume/Bruno_Dos_Santos_Resume.pdf"

    # ── Client-acquisition engine ────────────────────────────────────────────
    # The standing goal: bring in at least this many NEW CLIENTS per day. The
    # client engine sizes outreach volume to hit this at the funnel's measured
    # conversion rate, auto-ramping the knobs below within their safe ceilings.
    daily_client_target: int = 15
    client_autoscale_enabled: bool = True
    # Conservative cold→client conversion used until there's a real sample to
    # measure (industry cold-B2B is ~0.5–2%); the engine switches to the measured
    # rate once enough prospects have been contacted.
    client_default_conversion: float = 0.01
    # Safe ceilings the autoscaler will never exceed. Per-account send cap protects
    # mailbox reputation; per-business lead target keeps a single run timeout-safe.
    client_send_cap_ceiling: int = 500
    client_lead_target_ceiling: int = 600

    # Outbound mode: "send" (auto-send now), "send_on_approve", or "draft".
    gmail_outbound_mode: str = "send"
    # Safety cap on auto-sent outreach per day, per account (protects the mailbox).
    # Higher ceiling so a backlog clears faster; warmup still ramps a fresh mailbox
    # up to it gradually. Google Workspace allows ~2,000 sends/day, so 300 is well
    # within limits — lower it if a fresh mailbox ever gets flagged.
    gmail_daily_send_cap: int = 300
    # Deliverability warmup: ramp volume on a fresh mailbox so it isn't flagged
    # as spam. Effective cap = min(gmail_daily_send_cap, start + step × days_active).
    # Starts higher and ramps faster than before, so the queue drains in days, not
    # weeks, while still easing a brand-new mailbox in.
    email_warmup_enabled: bool = True
    email_warmup_start: int = 40
    email_warmup_step: int = 25

    # Insurance outreach to your imported personal contacts (warm network). Each
    # contact is emailed once; small daily batches drip through the list within
    # the mailbox warmup cap. SMS is OFF by default — automated marketing texts
    # need prior consent (TCPA); only enable if your list has opted in.
    contacts_outreach_batch: int = 20
    contacts_sms_enabled: bool = False
    # Emails to NEVER include in contacts outreach (family / personal). Comma-
    # separated, case-insensitive. Override via env to add/remove.
    contacts_outreach_exclude: str = (
        "brianadossantos@gmail.com,salasb2006@yahoo.com,brianadossantosawx@statefarm.com")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
