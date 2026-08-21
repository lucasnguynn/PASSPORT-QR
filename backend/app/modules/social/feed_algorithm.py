"""Deterministic social feed scoring and source composition."""
from datetime import UTC, datetime
from math import exp, log, sqrt
from typing import Protocol, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.social.models import CustomerStory


class Rankable(Protocol):
    id: object
    score: float


T = TypeVar("T", bound=Rankable)


def calculate_score(story: CustomerStory, now: datetime | None = None) -> float:
    """Calculate the exact Wilson/time-decay/media/length ranking score."""
    n = story.reaction_count + story.comment_count
    if n == 0 or story.published_at is None:
        return 0.0
    current = now or datetime.now(UTC)
    published = story.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    p = story.reaction_count / max(story.view_count, 1)
    z = 1.96
    # Clamp probability for numerical safety when legacy counters are inconsistent.
    p = min(1.0, max(0.0, p))
    wilson = (p + z**2 / (2 * n) - z * sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / (1 + z**2 / n)
    hours = max(0.0, (current - published).total_seconds() / 3600)
    decay = exp(-log(2) * hours / 72)
    media_bonus = 1.2 if story.media_urls else 1.0
    length_bonus = min(1.3, 1.0 + len(story.content) / 2000)
    return wilson * decay * media_bonus * length_bonus


async def calculate_and_update_score(story: CustomerStory, db: AsyncSession) -> float:
    """Recalculate and persist a story score after engagement changes."""
    story.score = calculate_score(story)
    await db.flush()
    return story.score


def merge_feed_sources(following: list[T], color: list[T], discovery: list[T], page: int, limit: int) -> list[T]:
    """Deduplicate the three prioritized sources, rank globally, and return a page."""
    seen: set[object] = set()
    result: list[T] = []
    for story in following + color + discovery:
        if story.id not in seen:
            seen.add(story.id)
            result.append(story)
    result.sort(key=lambda item: (-item.score, str(item.id)))
    return result[page * limit:(page + 1) * limit]
