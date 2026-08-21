"""Global discovery feed refresh task."""
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import session_factory
from app.core.redis_client import get_redis
from app.modules.social.models import CustomerStory
from app.workers.celery_app import celery_app


@celery_app.task(name="feed.refresh_discovery")
def refresh_discovery_feed() -> int:
    """Recompute the top thirty approved stories published in the last week."""
    return asyncio.run(_refresh_discovery_feed())


async def _refresh_discovery_feed() -> int:
    async with session_factory() as db:
        ids = list(await db.scalars(select(CustomerStory.id).where(CustomerStory.mod_status == "approved",
            CustomerStory.visibility == "public", CustomerStory.published_at >= datetime.now(UTC) - timedelta(days=7))
            .order_by(CustomerStory.score.desc()).limit(30)))
    redis = get_redis()
    try:
        async with redis.pipeline(transaction=True) as pipeline:
            pipeline.delete("feed:discovery:global")
            if ids:
                pipeline.rpush("feed:discovery:global", *(str(value) for value in ids))
            pipeline.expire("feed:discovery:global", 900)
            await pipeline.execute()
    finally:
        await redis.aclose()
    return len(ids)
