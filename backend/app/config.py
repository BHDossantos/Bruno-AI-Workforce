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
    # Cost-optimized default: gpt-4o-mini is ~15-20x cheaper than gpt-4o and is
    # plenty for drafting emails/texts and classifying replies. Override with
    # OPENAI_MODEL=gpt-4o only where you truly need the bigger model.
    openai_model: str = "gpt-4o-mini"
    # Autonomy scope. "all" runs every business's agents; "insurance" runs ONLY the
    # insurance agents/jobs (cost cut — skips music/bnb/savorymind/instagram/etc.).
    # Defaults to insurance-only so nothing off-brand (e.g. restaurant/consulting
    # cold emails) sends from the insurance domain. Flip to "all" to re-enable them.
    autonomy_profile: str = "insurance"
    # Per-business on/off (Setup → Businesses). Empty = follow autonomy_profile
    # (insurance-only by default); "true"/"false" explicitly overrides that one
    # business. Flip each on to run + test its agents & scheduled jobs. See
    # app/businesses.py.
    biz_insurance_enabled: str = ""
    biz_bnb_enabled: str = ""
    biz_savorymind_enabled: str = ""
    biz_music_enabled: str = ""
    biz_jobs_enabled: str = ""
    biz_content_enabled: str = ""
    embedding_model: str = "text-embedding-3-small"  # for the memory/knowledge layer
    image_model: str = "gpt-image-1"  # for auto-generated social post images
    # Jennifer voice assistant — real neural TTS so she sounds natural, not robotic.
    # "shimmer" is a warm, soft feminine voice; the instruction sets a sultry tone.
    voice_tts_model: str = "gpt-4o-mini-tts"
    voice_tts_voice: str = "coral"  # warmest, most natural feminine voice
    voice_tts_instructions: str = (
        "You are Jennifer, a real woman talking to someone she's close to — not an "
        "assistant reading a script. Sound completely human: relaxed, natural, "
        "conversational. Use easy, lifelike intonation with subtle pauses, soft "
        "breaths, and gentle ups and downs — the way a person actually talks. Warm, "
        "affectionate, with a soft sultry edge, but never performed, theatrical, or "
        "robotic. Slightly slower than average, smooth and intimate, like a quiet "
        "voice close to your ear. Vary your pacing naturally; don't sound flat or "
        "uniform.")

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
    # Insurance-specific gate: even when the global synthetic fallback is on for
    # other businesses, NEVER fabricate insurance leads (fake homeowners/partners
    # are pure junk that buries the real book). Flip on only to demo an empty DB.
    synthetic_insurance_leads: bool = False
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
    # Est. producer commission as a fraction of ANNUAL premium, for the Insurance
    # Commander's "commission today/expected" tiles (P&C new-business ~10-15%).
    insurance_commission_rate: float = 0.12
    # Speed target: leads should get a first touch within this many seconds
    # (EverQuote's core lesson — speed wins). Over it → the dashboard flags red.
    lead_response_target_seconds: int = 60
    # Producer identity stamped on personalized EverQuote outreach (email/SMS/
    # voicemail). Set to the licensed producer's real name + NPN license number.
    producer_name: str = "Bruno Dossantos"
    producer_license: str = "19029331"
    producer_callback: str = ""  # phone the voicemail/SMS asks them to call back
    # Recorded voicemail drop (producer's real voice) played by the auto-dialer when
    # a lead's call goes to voicemail. Set by recording via /calls/record-voicemail.
    producer_voicemail_url: str = ""
    # Email signature block for insurance outreach (business name comes from
    # insurance_business_name). Shown as:
    #   Thrust Insurance
    #   Bruno Dossantos | insurance agent
    #   phone# (833) 854-7055   Cell# 16039308272
    producer_title: str = "insurance agent"
    producer_office_phone: str = "(833) 854-7055"
    producer_cell: str = "16039308272"
    # Compliance & Governance — the single gate every autonomous outbound action
    # passes through (opt-out/DNC, contact-hour windows, per-state licensing,
    # required disclosures) with an immutable audit log. See app/compliance.py.
    compliance_enforce: bool = True        # master switch for the compliance gate
    licensed_states: str = "Massachusetts,New Hampshire,Florida"  # where the producer may sell
    call_daily_cap: int = 200              # max outbound calls/day (focus + carrier trust)
    # Specialized insurance agents. Commercial is the priority (higher commission,
    # stickier clients, more referrals) → biggest daily quota; home/auto + referral
    # partners run alongside for a balanced pipeline. Quotas are daily targets;
    # each run sources up to lead_batch_size and the agent runs several times a day.
    commercial_lead_daily_target: int = 200
    homeowner_lead_daily_target: int = 75
    referral_partner_daily_target: int = 25
    # Dedicated Home + Auto lead engines — find the real businesses that FEED each
    # personal line (realtors/lenders → home; dealers/repair → auto) in the
    # licensed states. Real OSM data; run several times a day toward these targets.
    home_lead_daily_target: int = 60
    auto_lead_daily_target: int = 60
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
    # Backup SMS provider (Plivo) — a Twilio-compatible carrier. When Twilio is down
    # or your account is deactivated, connect Plivo and texting keeps working with no
    # code change. sms_provider: "twilio" | "plivo" | "signalwire" | "auto" (auto =
    # whichever is connected; SignalWire preferred, then Twilio). "twilio" forces
    # Twilio. See app/integrations/plivo.py and app/integrations/telco.py.
    sms_provider: str = "auto"
    plivo_auth_id: str = ""
    plivo_auth_token: str = ""
    plivo_from_number: str = ""           # Plivo sending number (E.164, e.g. +1617...)
    plivo_voice_number: str = ""          # optional separate Plivo caller-ID for calls
    # Voice provider for calling: "auto" (Plivo if connected, else Twilio/SignalWire),
    # "plivo", "vonage", "twilio", "signalwire", or "sip". Lets calling move between
    # carriers when a number's carrier reputation is filtering calls to voicemail.
    voice_provider: str = "auto"
    # Self-hosted SIP softswitch (FreeSWITCH) — "build our own" origination. Instead
    # of a CPaaS HTTP API, we run FreeSWITCH ourselves and bring our own carrier (a
    # SIP trunk). The backend originates calls over the Event Socket (ESL) and serves
    # call control as FreeSWITCH HTTAPI from /calls/sip/*. See deploy/softswitch/.
    # NOTE: attestation/caller-reputation is still set by the SIP trunk carrier, so a
    # new trunk number must still be registered (freecallerregistry.com) to ring.
    sip_esl_host: str = "127.0.0.1"    # where FreeSWITCH's Event Socket listens
    sip_esl_port: int = 8021
    sip_esl_password: str = "ClueCon"  # secret — the ESL password from event_socket.conf
    sip_gateway: str = ""              # sofia gateway name for your BYOC trunk (e.g. "bruno_trunk")
    sip_from_number: str = ""          # caller ID presented on outbound calls (E.164)
    sip_voice_number: str = ""         # optional separate caller-ID for calls (falls back to sip_from_number)
    # Vonage (Nexmo) Voice — a third voice provider. Auth is a JWT signed with an
    # Application private key: create a Voice application in the Vonage dashboard,
    # link a number, and paste the Application ID + the downloaded private.key here.
    vonage_application_id: str = ""
    vonage_private_key: str = ""       # secret — the full PEM private key
    vonage_from_number: str = ""       # Vonage voice number (E.164)
    vonage_voice_number: str = ""      # optional separate caller-ID for calls
    # SignalWire — a Twilio-compatible carrier (same TwiML/REST) used as the drop-in
    # replacement when Twilio is unavailable. Powers BOTH voice + SMS through the
    # existing call/text logic. From your SignalWire Space: the Space URL, a Project
    # ID, and an API token; buy at least one SMS+Voice number in the Space.
    signalwire_space_url: str = "dossantosinsurance-org.signalwire.com"
    signalwire_project_id: str = "9909fc0c-553c-442d-bbf8-64ac8efe9b21"
    signalwire_api_token: str = ""        # secret (PT…) — paste in Setup, never commit
    signalwire_from_number: str = "+19788244228"   # default SMS+Voice number (E.164)
    signalwire_insurance_number: str = ""          # optional separate insurance SMS number
    signalwire_voice_number: str = ""              # optional separate caller-ID for calls
    # Twilio WhatsApp Business API — a legitimate, official channel (unlike
    # LinkedIn/consumer WhatsApp automation). Number must be WhatsApp-enabled in
    # the Twilio console (sandbox for testing, or an approved Twilio Sender for
    # production). E.164 format, e.g. +14155238886 — the "whatsapp:" prefix is
    # added automatically when sending.
    twilio_whatsapp_number: str = ""
    # WhatsApp via Meta's own Cloud API (no Twilio) — preferred over Twilio
    # WhatsApp when both are configured, since it has no reseller markup and
    # reuses the same Facebook Developer app already connected for FB/IG.
    whatsapp_cloud_phone_number_id: str = ""
    whatsapp_cloud_token: str = ""
    # ── Twilio Voice (calling) ────────────────────────────────────────────────
    # Caller-ID number for outbound calls (Voice-enabled Twilio number). Falls
    # back to the insurance/default SMS number when blank.
    twilio_voice_number: str = ""
    # Record calls + play a "this call may be recorded" notice (MA/FL are
    # two-party-consent states, so the notice is required when recording).
    call_recording_enabled: bool = True
    # Public base URL of THIS backend, so Twilio can reach our TwiML/status
    # webhooks (e.g. https://ai-workforce-...run.app). Set in the deploy env.
    public_base_url: str = ""
    # Browser softphone (Twilio Voice JS SDK) — needs an API Key + a TwiML App
    # whose Voice URL points at {public_base_url}/calls/twiml/outbound.
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""
    twilio_twiml_app_sid: str = ""

    # Newsletter banner photo per funnel (optional — a tasteful gradient banner
    # is used automatically when none is set, so newsletters never look bare).
    newsletter_banner_insurance: str = ""
    newsletter_banner_bnb: str = ""
    newsletter_banner_savorymind: str = ""
    newsletter_banner_music: str = ""
    # Auto-send a warm intro text when a lead replies to our email (becomes warm).
    sms_auto_on_reply: bool = True
    # SMS compliance + deliverability guards (applied to every autonomous/bulk send).
    sms_daily_send_cap: int = 50           # max texts per day across all numbers
    sms_send_window_start: int = 8         # earliest local hour to text (TCPA: 8am)
    sms_send_window_end: int = 21          # latest local hour to text (TCPA: 9pm)
    sms_timezone: str = "America/New_York"  # recipient tz (NH/MA/FL are all Eastern)
    # SMS follow-up: text leads who were emailed but never replied, N days later —
    # a second, higher-response channel. OFF by default (needs A2P 10DLC first);
    # flip on in Setup once texting is approved. The manual 'Text non-repliers'
    # button runs regardless. Every send still passes the compliance gate
    # (opt-out/hours/daily cap), so it can't text someone who opted out.
    sms_followup_enabled: bool = False
    sms_followup_delay_days: int = 2       # wait this long after the email before texting
    # Auto-reply to clearly-interested email replies: instead of only drafting the
    # AI response, SEND it immediately (with the booking link) so a hot lead gets an
    # answer in seconds — speed wins. OFF by default (keeps every reply human-reviewed);
    # only ever auto-sends to 'interested'/'question' replies, never ambiguous ones.
    auto_reply_enabled: bool = False

    # Daily auto-dial: at 8am the scheduler auto-calls the Call List (hottest first),
    # transferring live answers to the producer and dropping the recorded voicemail
    # otherwise. Gated by the same Outreach Autopilot / full-auto switch as auto-send.
    auto_dial_enabled: bool = True         # master switch for the daily 8am auto-dial pass
    auto_dial_daily_cap: int = 80          # max leads auto-dialed per day (protects your line)
    auto_dial_cooldown_days: int = 7       # don't auto-dial the same lead within N days
    # Transfer a LIVE answer to the producer's cell? Default OFF on a fresh number
    # whose reputation may filter calls to voicemail (a transfer would just hit the
    # producer's voicemail and waste the call). When off, the auto-dialer leaves the
    # recorded voicemail for everyone and the producer calls interested leads back.
    # Flip on once the number reliably rings.
    auto_dial_transfer_enabled: bool = False

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

    # Insurance account (PRIMARY) — Insurance agent outreach + insurance replies.
    insurance_gmail_address: str = ""
    insurance_google_oauth_client_id: str = ""
    insurance_google_oauth_client_secret: str = ""
    insurance_google_oauth_refresh_token: str = ""
    insurance_google_token_json: str = ""
    insurance_gmail_app_password: str = ""  # App Password for the primary insurance mailbox

    # Insurance account (BACKUP) — a second insurance mailbox (e.g. a second
    # agency domain). Used automatically when the primary can't send.
    insurance_backup_gmail_address: str = ""
    insurance_backup_google_oauth_client_id: str = ""
    insurance_backup_google_oauth_client_secret: str = ""
    insurance_backup_google_oauth_refresh_token: str = ""
    insurance_backup_google_token_json: str = ""
    insurance_backup_gmail_app_password: str = ""

    # BnB Global account — dedicated mailbox for consulting outreach (keeps it off
    # the personal Gmail). Connect via App Password or OAuth, same as the others.
    bnb_gmail_address: str = "braxandbrie@gmail.com"
    bnb_google_oauth_client_id: str = ""
    bnb_google_oauth_client_secret: str = ""
    bnb_google_oauth_refresh_token: str = ""
    bnb_google_token_json: str = ""
    bnb_gmail_app_password: str = ""

    # SavoryMind account — dedicated mailbox for restaurant (SavoryMind) outreach.
    savorymind_gmail_address: str = "taste@savorymindfood.com"
    savorymind_google_oauth_client_id: str = ""
    savorymind_google_oauth_client_secret: str = ""
    savorymind_google_oauth_refresh_token: str = ""
    savorymind_google_token_json: str = ""
    savorymind_gmail_app_password: str = ""
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
    calendar_link: str = ""     # default booking link (Calendly/Cal.com) added to email CTAs
    # Per-business booking links: a prospect of each business books the right
    # calendar. Empty falls back to the default calendar_link above.
    calendar_link_insurance: str = ""
    calendar_link_bnb: str = ""
    calendar_link_savorymind: str = ""

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
    # Enables the in-app "Connect with Facebook/Instagram" one-click button. Must
    # be registered as a Valid OAuth Redirect URI in the Meta app and point at this
    # backend's callback, e.g. https://<backend>/connections/meta/oauth/callback
    meta_redirect_uri: str = ""
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
    # NOTE: a personal Gmail App Password gets revoked/flagged by Google if it sends
    # cold email at volume. The client-goal autoscaler will raise gmail_daily_send_cap
    # up to THIS ceiling to hit a target — so it must be ≥ the send cap, or it pulls
    # sending back down. 200 to match the 200/day target (dedicated provider: Resend).
    client_send_cap_ceiling: int = 200
    client_lead_target_ceiling: int = 600

    # Instantly.ai — dedicated cold-email engine (many warmed inboxes + deliverability
    # + sequences). When both are set, outreach is handed to Instantly instead of the
    # personal Gmail (which Google revokes at volume). Reference {{personalization}}
    # in the Instantly campaign's email step to send our AI-written copy.
    instantly_api_key: str = ""
    instantly_campaign_id: str = ""
    # Smartlead.ai — same idea as Instantly (the app picks whichever is connected).
    smartlead_api_key: str = ""
    smartlead_campaign_id: str = ""
    # SendGrid — reliable DELIVERY (we keep our copy + sequences; SendGrid just sends).
    # Requires a VERIFIED sender. Used for direct sends when Gmail is too fragile.
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""  # default / personal sender
    # Per-business verified senders (SendGrid Single Sender) so each business sends
    # AS its own brand. Defaults match the verified senders already set up.
    sendgrid_from_insurance: str = "b@dossantosinsurance.org"
    sendgrid_from_bnb: str = "braxandbrie@gmail.com"
    sendgrid_from_savorymind: str = "taste@savorymindfood.com"
    # Optional per-business Reply-To (where replies land). Blank → replies go to the
    # from-address. Lets BnB send AS hello@bnbglobal.net but route replies to a
    # monitored inbox without a mailbox on the sending domain.
    sendgrid_replyto_insurance: str = ""
    sendgrid_replyto_bnb: str = "braxandbrie@gmail.com"
    sendgrid_replyto_savorymind: str = ""
    # SendGrid's GLOBAL daily send cap (across all businesses). On the free trial
    # SendGrid allows ~100/day, so keep this at 90 until the paid plan is active;
    # raise it after the upgrade.
    sendgrid_daily_cap: int = 200   # global daily cap when sending via SendGrid

    # Resend — modern email API with great deliverability on your own domain.
    # Preferred over SendGrid/Gmail when connected. Verify your domain in Resend
    # (add its DNS records) so you can send AS b@dossantosinsurance.org. Replies go
    # to resend_reply_to (a mailbox you actually read) if set, else the from-address.
    resend_api_key: str = ""
    resend_from_email: str = ""                 # default sender (verified-domain address)
    resend_from_insurance: str = "b@dossantosinsurance.org"
    resend_reply_to: str = ""                   # where replies land (a monitored inbox)
    # Optional Svix signing secret ("whsec_…") for the Resend inbound/event webhook.
    # When set, incoming webhook posts are signature-verified; when blank the endpoint
    # accepts them unauthenticated (same as the Twilio/Plivo inbound webhooks).
    resend_webhook_secret: str = ""

    # Outbound mode: "send" (auto-send now), "send_on_approve", or "draft".
    gmail_outbound_mode: str = "send"
    # Safety cap on auto-sent outreach per day, per account (protects the mailbox).
    # 200/day per Bruno's target. Google Workspace allows ~2,000 sends/day, so this
    # is well within limits — lower it if a fresh mailbox ever gets flagged.
    gmail_daily_send_cap: int = 200
    # Deliverability warmup: ramp volume on a fresh mailbox so it isn't flagged as
    # spam. Effective cap = min(gmail_daily_send_cap, start + step × days_active). A
    # warmed mailbox (many days active) is already at the ceiling; a brand-new one
    # climbs 100 → 200 over ~4 days. Runtime-adjustable in Setup.
    email_warmup_enabled: bool = True
    email_warmup_start: int = 100
    email_warmup_step: int = 25

    # ── Domain-level send pacing (protects a NEW sending domain's reputation) ──
    # Both the auto-send autopilot AND the manual "Send drafts" button honor these,
    # so total emails/day from the domain never spike — spikes from a fresh domain
    # get the whole domain flagged as spam by Gmail/Outlook.
    #
    # Steady-state cap once warmed:
    email_daily_send_cap: int = 70
    # One-off warm-up ramp to clear an initial backlog on a fresh domain WITHOUT
    # getting flagged: a comma list of per-day caps counted from email_rampup_start
    # (element 0 = the start date, element 1 = the next day, …). After the list is
    # exhausted the steady email_daily_send_cap applies. Ramps ~1,900 over ~5 days.
    # Set email_rampup_start blank to disable the ramp (just use the steady cap).
    email_rampup_schedule: str = "300,400,500,500,300"
    email_rampup_start: str = "2026-07-14"  # ISO date the ramp begins (blank = off)

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
