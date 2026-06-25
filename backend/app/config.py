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
    # Cities the lead-finder agents search for real businesses (free, via
    # OpenStreetMap). Comma-separated. Drives commercial insurance + restaurant
    # sourcing with real, deliverable emails at no cost.
    lead_cities: str = "Boston,New York,Miami,Chicago,Austin"
    # Whole STATES to search (OSM names, comma-separated). When set, these take
    # precedence over lead_cities and give a much wider lead pool — the engine
    # pulls email-tagged businesses from across the entire state.
    lead_states: str = "Massachusetts,New Hampshire,Florida"
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
    browser_auto_submit: bool = False  # human-in-the-loop by default — review before submit
    # Applicant identity used to fill application forms.
    applicant_name: str = "Bruno Dos Santos"
    applicant_email: str = "brunodossantos707@gmail.com"
    applicant_phone: str = "603-930-8272"
    applicant_linkedin: str = ""  # set to your LinkedIn URL
    applicant_github: str = "https://github.com/BHDossantos"
    applicant_location: str = "Boston, MA"
    # Resume PDF baked into the backend image (see backend/assets/resume/); the
    # browser worker attaches it to file uploads. Override via env if needed.
    applicant_resume_path: str = "/app/assets/resume/Bruno_Dos_Santos_Resume.pdf"

    # Outbound mode: "send" (auto-send now), "send_on_approve", or "draft".
    gmail_outbound_mode: str = "send"
    # Safety cap on auto-sent outreach per day, per account (protects the mailbox).
    # Sized for the 3×/day lead passes; lower it if a fresh mailbox gets flagged.
    gmail_daily_send_cap: int = 120
    # Deliverability warmup: ramp volume on a fresh mailbox so it isn't flagged
    # as spam. Effective cap = min(gmail_daily_send_cap, start + step × days_active).
    email_warmup_enabled: bool = True
    email_warmup_start: int = 20
    email_warmup_step: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
