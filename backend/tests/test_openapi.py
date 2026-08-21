import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/dpp")
os.environ.setdefault("REDIS_URL", "redis://:pass@localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-at-least-thirty-two-characters")
os.environ.setdefault("ECDSA_PRIVATE_KEY_B64", "test")
os.environ.setdefault("ECDSA_PUBLIC_KEY_B64", "test")

from app.main import create_app


def test_openapi_schema_is_generated() -> None:
    schema = create_app().openapi()
    assert schema["info"]["title"] == "Digital Product Passport API"
    assert "/health" in schema["paths"]
