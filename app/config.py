"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # DB
    database_url: str = "sqlite:///./local.db"
    # Auth
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_VERY_SECRET_KEY"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days

    # App
    app_name: str = "YM Unit Economy"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
