"""Public, customer, and administrator SocialModule endpoints."""
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.redis_client import get_redis
from app.modules.passport.router import require_customer
from app.modules.qr.router import bearer, limiter, require_admin
from app.modules.social.models import CustomerStory, Follow, User
from app.modules.social.schemas import FeedResponse, FollowResponse, ReactionRequest, ReactionResponse, RejectRequest, StoryCreate, StoryResponse, StoryUpdate
from app.modules.social.service import SocialNotFoundError, SocialPermissionError, create_story, get_feed, resolve_user, set_reaction, update_story
from app.workers.tasks.feed_fanout import fanout_story

router = APIRouter(prefix="/api/social", tags=["social"])
admin_router = APIRouter(prefix="/api/admin/social", tags=["social-admin"])


async def optional_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: Annotated[AsyncSession, Depends(get_session)]) -> User | None:
    """Resolve an optional, valid customer token; invalid supplied tokens are rejected."""
    if credentials is None:
        return None
    settings = get_settings()
    try:
        claims: dict[str, object] = jwt.decode(credentials.credentials, settings.keycloak_public_key.replace("\\n", "\n"),
            algorithms=["RS256"], audience=settings.keycloak_audience, issuer=settings.keycloak_issuer)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    return await resolve_user(claims, db)


async def authenticated_user(claims: Annotated[dict[str, object], Depends(require_customer)], db: Annotated[AsyncSession, Depends(get_session)]) -> User:
    """Resolve the authenticated customer's persisted social profile."""
    return await resolve_user(claims, db)


@router.get("/feed", response_model=FeedResponse)
@limiter.limit("60/minute")
async def feed(request: Request, db: Annotated[AsyncSession, Depends(get_session)], redis: Annotated[Redis, Depends(get_redis)],
               user: Annotated[User | None, Depends(optional_user)], page: Annotated[int, Query(ge=0)] = 0,
               limit: Annotated[int, Query(ge=1, le=100)] = 20) -> FeedResponse:
    """Return discovery for guests or a personalized, ranked feed for customers."""
    items = await get_feed(db, redis, user, page, limit)
    return FeedResponse(items=[StoryResponse.model_validate(item) for item in items], page=page, limit=limit)


@router.get("/stories/by-color/{color_tag}", response_model=list[StoryResponse])
@limiter.limit("60/minute")
async def stories_by_color(request: Request, color_tag: str, db: Annotated[AsyncSession, Depends(get_session)]) -> list[CustomerStory]:
    """List approved public stories matching an exact gem color tag."""
    rows = await db.scalars(select(CustomerStory).where(CustomerStory.color_tag == color_tag, CustomerStory.mod_status == "approved",
        CustomerStory.visibility == "public").order_by(CustomerStory.score.desc()).limit(100))
    return list(rows)


@router.get("/stories/{story_id}", response_model=StoryResponse)
@limiter.limit("60/minute")
async def story_detail(request: Request, story_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]) -> CustomerStory:
    """Return an approved public story and record a view."""
    story = await db.get(CustomerStory, story_id)
    if story is None or story.mod_status != "approved" or story.visibility != "public":
        raise HTTPException(status_code=404, detail="Story not found")
    story.view_count += 1
    await db.commit()
    await db.refresh(story)
    return story


@router.post("/stories", response_model=StoryResponse, status_code=201)
async def post_story(data: StoryCreate, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> CustomerStory:
    """Create and automatically moderate a customer product story."""
    try:
        story = await create_story(data, user, db)
    except SocialNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    if story.mod_status == "approved":
        fanout_story.delay(str(story.id))
    return story


@router.patch("/stories/{story_id}", response_model=StoryResponse)
async def patch_story(story_id: UUID, data: StoryUpdate, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> CustomerStory:
    """Update an owned story and submit changed content to moderation."""
    try:
        return await update_story(story_id, data, user, db)
    except SocialNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Story not found") from exc
    except SocialPermissionError as exc:
        raise HTTPException(status_code=403, detail="Story ownership required") from exc


@router.delete("/stories/{story_id}", status_code=204)
async def remove_story(story_id: UUID, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> Response:
    """Permanently delete an owned story and its cascading reactions."""
    story = await db.get(CustomerStory, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.author_id != user.id:
        raise HTTPException(status_code=403, detail="Story ownership required")
    await db.delete(story)
    await db.commit()
    return Response(status_code=204)


@router.post("/stories/{story_id}/react", response_model=ReactionResponse)
async def react(story_id: UUID, data: ReactionRequest, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> ReactionResponse:
    """Create or replace the customer's single reaction to a public story."""
    story = await db.get(CustomerStory, story_id)
    if story is None or story.mod_status != "approved":
        raise HTTPException(status_code=404, detail="Story not found")
    return ReactionResponse(reaction_count=await set_reaction(story, user, data.reaction_type, db))


@router.delete("/stories/{story_id}/react", response_model=ReactionResponse)
async def unreact(story_id: UUID, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> ReactionResponse:
    """Remove the customer's reaction from a story idempotently."""
    story = await db.get(CustomerStory, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return ReactionResponse(reaction_count=await set_reaction(story, user, None, db))


@router.post("/users/{following_id}/follow", response_model=FollowResponse)
async def follow(following_id: UUID, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> FollowResponse:
    """Follow another local social profile idempotently."""
    if following_id == user.id:
        raise HTTPException(status_code=400, detail="Users cannot follow themselves")
    if await db.get(User, following_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if await db.get(Follow, (user.id, following_id)) is None:
        db.add(Follow(follower_id=user.id, following_id=following_id))
        await db.commit()
    return FollowResponse(following=True)


@router.delete("/users/{following_id}/follow", response_model=FollowResponse)
async def unfollow(following_id: UUID, user: Annotated[User, Depends(authenticated_user)], db: Annotated[AsyncSession, Depends(get_session)]) -> FollowResponse:
    """Stop following a profile idempotently."""
    await db.execute(delete(Follow).where(Follow.follower_id == user.id, Follow.following_id == following_id))
    await db.commit()
    return FollowResponse(following=False)


@admin_router.get("/moderation-queue", response_model=list[StoryResponse])
async def moderation_queue(db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[dict[str, object], Depends(require_admin)]) -> list[CustomerStory]:
    """List stories requiring a moderator decision, oldest first."""
    return list(await db.scalars(select(CustomerStory).where(CustomerStory.mod_status == "pending").order_by(CustomerStory.created_at)))


@admin_router.post("/stories/{story_id}/approve", response_model=StoryResponse)
async def approve_story(story_id: UUID, db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[dict[str, object], Depends(require_admin)]) -> CustomerStory:
    """Approve and publish a moderated story, then enqueue follower fan-out."""
    story = await db.get(CustomerStory, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    story.mod_status, story.mod_note, story.published_at = "approved", None, datetime.now(UTC)
    await db.commit(); await db.refresh(story)
    fanout_story.delay(str(story.id))
    return story


@admin_router.post("/stories/{story_id}/reject", response_model=StoryResponse)
async def reject_story(story_id: UUID, data: RejectRequest, db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[dict[str, object], Depends(require_admin)]) -> CustomerStory:
    """Reject a moderated story with a human-readable reason."""
    story = await db.get(CustomerStory, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    story.mod_status, story.mod_note, story.published_at = "rejected", data.reason, None
    await db.commit(); await db.refresh(story)
    return story
