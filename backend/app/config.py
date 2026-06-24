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
    # When False, agents use ONLY live-sourced data (no synthetic top-up to hit
    # target counts). Set False in production once real sourcing is in place.
    allow_synthetic_fallback: bool = True
    # Cities the lead-finder agents search for real businesses (free, via
    # OpenStreetMap). Comma-separated. Drives commercial insurance + restaurant
    # sourcing with real, deliverable emails at no cost.
    lead_cities: str = "Boston,New York,Miami,Chicago,Austin"
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

    # Insurance account — Insurance agent outreach + the report's insurance replies.
    insurance_gmail_address: str = "bruno@thrustinsurance.com"
    insurance_google_oauth_client_id: str = ""
    insurance_google_oauth_client_secret: str = ""
    insurance_google_oauth_refresh_token: str = ""
    insurance_google_token_json: str = ""

    # Email template / signature (applied to every outbound email for a
    # consistent look + CAN-SPAM compliant footer).
    sender_name: str = "Bruno Dos Santos"
    personal_business_name: str = ""
    insurance_business_name: str = "Thrust Insurance"
    company_address: str = ""  # physical mailing address shown in the footer
    calendar_link: str = ""     # booking link (Calendly/Cal.com) added to email CTAs

    # Outbound mode: "send" (auto-send now), "send_on_approve", or "draft".
    gmail_outbound_mode: str = "send"
    # Safety cap on auto-sent outreach per day, per account (protects the mailbox).
    gmail_daily_send_cap: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
