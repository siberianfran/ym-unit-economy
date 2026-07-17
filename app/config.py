"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./local.db"
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_VERY_SECRET_KEY"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30

    app_name: str = "YM Unit Economy"
    app_url: str = "https://www.marja.app"
    debug: bool = False

    resend_api_key: str = ""
    email_from: str = "MARJA <noreply@marja.app>"
    password_reset_expire_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
