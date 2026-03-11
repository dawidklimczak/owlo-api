from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # AI
    TAVILY_API_KEY: str
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4.1-nano"

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # Email
    EMAIL_PROVIDER: Literal["resend", "smtp"] = "resend"
    RESEND_API_KEY: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@pulsefeed.app"

    # URLs
    APP_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"
    COOKIE_DOMAIN: str = "localhost"

    # Business logic
    DEFAULT_CHECK_INTERVAL_DAYS: int = 7
    MAX_SEARCH_RESULTS_PER_TOPIC: int = 5

    # Magic link
    MAGIC_LINK_EXPIRE_MINUTES: int = 15


settings = Settings()
