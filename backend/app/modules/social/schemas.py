"""Pydantic v2 contracts for the SocialModule API."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Visibility = Literal["public", "private", "followers"]
ReactionType = Literal["love", "sparkle", "inspired"]


class StoryCreate(BaseModel):
    product_id: UUID
    title: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    color_tag: str | None = Field(default=None, max_length=50)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    media_urls: list[str] = Field(default_factory=list, max_length=10)
    visibility: Visibility = "public"

    @field_validator("media_urls")
    @classmethod
    def validate_media_urls(cls, values: list[str]) -> list[str]:
        """Accept only externally retrievable HTTP(S) media references."""
        if any(not value.startswith(("https://", "http://")) for value in values):
            raise ValueError("media URLs must use HTTP or HTTPS")
        return values


class StoryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    color_tag: str | None = Field(default=None, max_length=50)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    media_urls: list[str] | None = Field(default=None, max_length=10)
    visibility: Visibility | None = None


class StoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    author_id: UUID
    product_id: UUID
    title: str | None
    content: str
    color_tag: str | None
    color_hex: str | None
    media_urls: list[str]
    visibility: str
    score: float
    view_count: int
    reaction_count: int
    comment_count: int
    mod_status: str
    mod_note: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FeedResponse(BaseModel):
    items: list[StoryResponse]
    page: int
    limit: int


class ReactionRequest(BaseModel):
    reaction_type: ReactionType


class ReactionResponse(BaseModel):
    reaction_count: int


class FollowResponse(BaseModel):
    following: bool


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
