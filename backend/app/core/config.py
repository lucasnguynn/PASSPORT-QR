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
    colora_aes_key_b64: str = ""
    active_key_id: str = "1"
    keycloak_url: str = "http://keycloak:8080/auth"
    keycloak_realm: str = "dpp"
    keycloak_issuer: str = "http://keycloak:8080/auth/realms/dpp"
    keycloak_audience: str = "account"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_secure: bool = False
    minio_public_url: str = "http://localhost:9000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""
    return Settings()  # type: ignore[call-arg]
