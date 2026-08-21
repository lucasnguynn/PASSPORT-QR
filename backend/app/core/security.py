"""Keycloak access-token validation and authorization dependencies."""

import json
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.redis_client import get_redis
from app.modules.social.models import User

bearer = HTTPBearer(auto_error=False)
JWKS_TTL_SECONDS = 3600


async def _get_jwks(redis: Redis, force_refresh: bool = False) -> dict[str, Any]:
    """Return Keycloak's JWKS, refreshing the one-hour Redis cache when absent."""
    settings = get_settings()
    cache_key = f"auth:jwks:{settings.keycloak_realm}"
    cached = None if force_refresh else await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    url = (
        f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks: dict[str, Any] = response.json()
    await redis.set(cache_key, json.dumps(jwks), ex=JWKS_TTL_SECONDS)
    return jwks


async def validate_access_token(token: str, redis: Redis) -> dict[str, Any]:
    """Validate token signature, expiration, issuer, and audience against Keycloak JWKS."""
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        jwks = await _get_jwks(redis)
        key = next((item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None)
        if key is None:
            jwks = await _get_jwks(redis, force_refresh=True)
            key = next(item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid"))
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.keycloak_issuer,
            audience=settings.keycloak_audience,
            options={"verify_exp": True, "verify_iss": True, "verify_aud": True},
        )
    except (JWTError, KeyError, StopIteration, ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Access token has no subject")
    return claims


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    """Validate a bearer token and create its local user profile on first login."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = await validate_access_token(credentials.credentials, redis)
    keycloak_id = str(claims["sub"])
    user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))
    if user is None:
        username = str(claims.get("preferred_username") or f"user-{keycloak_id[:12]}")[:100]
        user = User(
            keycloak_id=keycloak_id,
            username=username,
            display_name=str(claims.get("name"))[:255] if claims.get("name") else None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    setattr(user, "auth_roles", frozenset(claims.get("realm_access", {}).get("roles", [])))
    return user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User | None:
    """Return an authenticated local user when a bearer token is supplied."""
    if credentials is None:
        return None
    return await get_current_user(credentials, db, redis)


def _require_role(user: User, role: str) -> User:
    if role not in getattr(user, "auth_roles", frozenset()):
        raise HTTPException(status_code=403, detail=f"{role.title()} role required")
    return user


async def require_customer(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Require the Keycloak customer realm role."""
    return _require_role(user, "customer")


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Require the Keycloak admin realm role."""
    return _require_role(user, "admin")


__all__ = ["bearer", "get_current_user", "get_optional_user", "require_admin", "require_customer"]
