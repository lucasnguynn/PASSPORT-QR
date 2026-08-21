"""Shared Redis-backed API rate limiter."""

from typing import Any

from fastapi import Request
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


def authenticated_subject_or_ip(request: Request) -> str:
    """Key authenticated quotas by JWT subject and fall back to the remote IP."""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        try:
            claims: dict[str, Any] = jwt.get_unverified_claims(authorization[7:])
            if claims.get("sub"):
                return f"user:{claims['sub']}"
        except JWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().redis_url)
