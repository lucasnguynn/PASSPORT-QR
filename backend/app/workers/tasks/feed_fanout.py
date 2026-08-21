"""Follower feed materialization tasks."""
import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.database import session_factory
from app.core.redis_client import get_redis
from app.modules.social.models import CustomerStory, Follow
from app.workers.celery_app import celery_app


@celery_app.task(name="feed.fanout_story")
def fanout_story(story_id: str) -> int:
    """Push an approved story to follower lists, unless its author is a celebrity."""
    return asyncio.run(_fanout_story(UUID(story_id)))


async def _fanout_story(story_id: UUID) -> int:
    async with session_factory() as db:
        story = await db.get(CustomerStory, story_id)
        if story is None or story.mod_status != "approved":
            return 0
        followers = list(await db.scalars(select(Follow.follower_id).where(Follow.following_id == story.author_id).limit(10001)))
    if len(followers) > 10000:
        return 0
    redis = get_redis()
    try:
        async with redis.pipeline(transaction=False) as pipeline:
            for follower_id in followers:
                pipeline.lpush(f"feed:following:{follower_id}", str(story_id))
                pipeline.ltrim(f"feed:following:{follower_id}", 0, 999)
            if followers:
                await pipeline.execute()
    finally:
        await redis.aclose()
    return len(followers)
