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
    instantly_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
