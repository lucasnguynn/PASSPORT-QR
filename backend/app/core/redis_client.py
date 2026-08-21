from redis.asyncio import Redis

from app.core.config import get_settings


def get_redis() -> Redis:
    """Create an asynchronous Redis client from configured credentials."""
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
