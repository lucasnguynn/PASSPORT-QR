"""Relational models owned by the social bounded context."""
import uuid
from datetime import datetime

from sqlalchemy import CHAR, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    """A local profile mapped one-to-one to a Keycloak identity."""
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keycloak_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerStory(Base):
    """A customer-authored product story awaiting or passing moderation."""
    __tablename__ = "customer_stories"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    color_tag: Mapped[str | None] = mapped_column(String(50), index=True)
    color_hex: Mapped[str | None] = mapped_column(CHAR(7))
    media_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    visibility: Mapped[str] = mapped_column(String(20), default="public", server_default="public")
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reaction_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    comment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mod_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    mod_note: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    author: Mapped[User] = relationship()
    reactions: Mapped[list["StoryReaction"]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("visibility IN ('public','private','followers')", name="ck_story_visibility"),
        CheckConstraint("mod_status IN ('pending','approved','rejected','flagged')", name="ck_story_mod_status"),
        Index("ix_customer_stories_score_desc", score.desc()),
    )


class StoryReaction(Base):
    __tablename__ = "story_reactions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    story_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_stories.id", ondelete="CASCADE"))
    reaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (PrimaryKeyConstraint("user_id", "story_id"), CheckConstraint("reaction_type IN ('love','sparkle','inspired')", name="ck_reaction_type"))


class Follow(Base):
    __tablename__ = "follows"
    follower_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    following_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (PrimaryKeyConstraint("follower_id", "following_id"), CheckConstraint("follower_id <> following_id", name="ck_no_self_follow"))
