from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    database_url: str
    redis_url: str
    secret_key: str
    environment: str = "development"
    qr_uri_scheme: str = "dppassport"
    ecdsa_private_key_b64: str
    ecdsa_public_key_b64: str
    active_key_id: str = "key_001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""
    return Settings()  # type: ignore[call-arg]
