from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or .env file."""

    API_KEY: str = "tronn_sec_token_889900"
    APP_NAME: str = "Tronn Data Sync API"
    APP_VERSION: str = "1.0.0"
    DEVELOPER: str = "Tronn"
    ENVIRONMENT: str = "development"
    DB_PATH: str = "data/db.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance."""
    return Settings()


settings = get_settings()

