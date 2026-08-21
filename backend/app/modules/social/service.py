"""Transactional application services for social stories and feeds."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.passport.models import Product
from app.modules.social.feed_algorithm import calculate_and_update_score, merge_feed_sources
from app.modules.social.models import CustomerStory, Follow, StoryReaction, User
from app.modules.social.moderation import auto_moderate
from app.modules.social.schemas import StoryCreate, StoryUpdate


class SocialNotFoundError(Exception):
    """Requested social resource is absent or not visible."""


class SocialPermissionError(Exception):
    """Authenticated user does not own the requested resource."""


async def resolve_user(claims: dict[str, object], db: AsyncSession) -> User:
    """Resolve a Keycloak subject to its local social profile, creating it on first use."""
    subject = str(claims["sub"])
    user = await db.scalar(select(User).where(User.keycloak_id == subject))
    if user is not None:
        return user
    base_username = str(claims.get("preferred_username") or f"user-{subject[:8]}")[:100]
    username = base_username
    suffix = 0
    while await db.scalar(select(User.id).where(User.username == username)) is not None:
        suffix += 1
        username = f"{base_username[:90]}-{suffix}"
    user = User(keycloak_id=subject, username=username, display_name=str(claims.get("name") or "") or None)
    db.add(user)
    await db.flush()
    return user


async def create_story(data: StoryCreate, user: User, db: AsyncSession) -> CustomerStory:
    """Validate product/content, moderate, persist, and return a story."""
    if await db.get(Product, data.product_id) is None:
        raise SocialNotFoundError
    since = datetime.now(UTC) - timedelta(hours=24)
    duplicates = await db.scalar(select(func.count()).select_from(CustomerStory).where(
        CustomerStory.author_id == user.id, CustomerStory.content == data.content, CustomerStory.created_at >= since))
    moderation = auto_moderate(data.content, data.title)
    if (duplicates or 0) >= 3:
        moderation = type(moderation)("flagged", "spam")
    approved = moderation.status == "approved"
    story = CustomerStory(author_id=user.id, **data.model_dump(), mod_status="approved" if approved else "pending",
                          mod_note=moderation.reason, published_at=datetime.now(UTC) if approved else None)
    db.add(story)
    await db.commit()
    await db.refresh(story)
    return story


async def update_story(story_id: UUID, data: StoryUpdate, user: User, db: AsyncSession) -> CustomerStory:
    """Update an owned story and re-run moderation when its text changes."""
    story = await db.get(CustomerStory, story_id)
    if story is None:
        raise SocialNotFoundError
    if story.author_id != user.id:
        raise SocialPermissionError
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(story, key, value)
    moderation = auto_moderate(story.content, story.title)
    story.mod_status = "approved" if moderation.status == "approved" else "pending"
    story.mod_note = moderation.reason
    if story.mod_status == "approved" and story.published_at is None:
        story.published_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(story)
    return story


async def get_feed(db: AsyncSession, redis: Redis, user: User | None, page: int, limit: int) -> list[CustomerStory]:
    """Read allocated following/color/discovery candidates then merge and rank them."""
    discovery_ids = await redis.lrange("feed:discovery:global", 0, 99)
    discovery = await _ordered_candidates(db, discovery_ids, 3)
    if user is None:
        if discovery:
            return merge_feed_sources([], [], discovery, page, limit)
        rows = await db.scalars(select(CustomerStory).where(CustomerStory.mod_status == "approved", CustomerStory.visibility == "public")
                                .order_by(CustomerStory.score.desc()).offset(page * limit).limit(limit))
        return list(rows)
    following_ids = await redis.lrange(f"feed:following:{user.id}", 0, 99)
    following = await _ordered_candidates(db, following_ids, 12)
    colors = (await db.scalars(select(distinct(Product.gem_color)).join(CustomerStory, CustomerStory.product_id == Product.id)
                               .where(CustomerStory.author_id == user.id, Product.gem_color.is_not(None)))).all()
    color_rows: list[CustomerStory] = []
    if colors:
        result = await db.scalars(select(CustomerStory).where(CustomerStory.color_tag.in_(colors), CustomerStory.mod_status == "approved",
            CustomerStory.visibility == "public", CustomerStory.author_id != user.id,
            CustomerStory.published_at > datetime.now(UTC) - timedelta(days=30)).order_by(CustomerStory.score.desc()).limit(5))
        color_rows = list(result)
    return merge_feed_sources(following, color_rows, discovery, page, limit)


async def _ordered_candidates(db: AsyncSession, raw_ids: list[str], limit: int) -> list[CustomerStory]:
    valid: list[UUID] = []
    for value in raw_ids:
        try:
            valid.append(UUID(value))
        except ValueError:
            continue
    if not valid:
        return []
    rows = await db.scalars(select(CustomerStory).where(CustomerStory.id.in_(valid), CustomerStory.mod_status == "approved",
        CustomerStory.visibility == "public").order_by(CustomerStory.score.desc()).limit(limit))
    return list(rows)


async def set_reaction(story: CustomerStory, user: User, reaction_type: str | None, db: AsyncSession) -> int:
    """Upsert or remove one user's reaction and atomically refresh counters/score."""
    reaction = await db.get(StoryReaction, (user.id, story.id))
    if reaction_type is None and reaction is not None:
        await db.delete(reaction)
    elif reaction_type is not None:
        if reaction is None:
            db.add(StoryReaction(user_id=user.id, story_id=story.id, reaction_type=reaction_type))
        else:
            reaction.reaction_type = reaction_type
    await db.flush()
    story.reaction_count = int(await db.scalar(select(func.count()).select_from(StoryReaction).where(StoryReaction.story_id == story.id)) or 0)
    await calculate_and_update_score(story, db)
    await db.commit()
    return story.reaction_count
