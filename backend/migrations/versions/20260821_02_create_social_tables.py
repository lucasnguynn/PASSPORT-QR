"""create social network tables and search indexes

Revision ID: 20260821_02
Revises: 20260821_01
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260821_02"
down_revision: str | None = "20260821_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create profiles, stories, reactions, follows, and their feed/search indexes."""
    op.create_table("users", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("keycloak_id", sa.String(255), nullable=False), sa.Column("username", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255)), sa.Column("avatar_url", sa.Text()), sa.Column("bio", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("keycloak_id"), sa.UniqueConstraint("username"))
    op.create_index("ix_users_keycloak_id", "users", ["keycloak_id"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table("customer_stories", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255)), sa.Column("content", sa.Text(), nullable=False), sa.Column("color_tag", sa.String(50)),
        sa.Column("color_hex", sa.CHAR(7)), sa.Column("media_urls", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("visibility", sa.String(20), server_default="public", nullable=False), sa.Column("score", sa.Float(), server_default="0", nullable=False),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False), sa.Column("reaction_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("comment_count", sa.Integer(), server_default="0", nullable=False), sa.Column("mod_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("mod_note", sa.Text()), sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.CheckConstraint("visibility IN ('public','private','followers')", name="ck_story_visibility"),
        sa.CheckConstraint("mod_status IN ('pending','approved','rejected','flagged')", name="ck_story_mod_status"))
    for column in ("author_id", "product_id", "color_tag", "score", "mod_status"):
        op.create_index(f"ix_customer_stories_{column}", "customer_stories", [column])
    op.create_index("ix_customer_stories_score_desc", "customer_stories", [sa.text("score DESC")])
    op.execute("CREATE INDEX ix_customer_stories_search ON customer_stories USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || content))")
    op.create_table("story_reactions", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("reaction_type", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["story_id"], ["customer_stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "story_id"), sa.CheckConstraint("reaction_type IN ('love','sparkle','inspired')", name="ck_reaction_type"))
    op.create_table("follows", sa.Column("follower_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("following_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["following_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("follower_id", "following_id"), sa.CheckConstraint("follower_id <> following_id", name="ck_no_self_follow"))
    op.create_index("ix_follows_following_id", "follows", ["following_id"])


def downgrade() -> None:
    """Drop all social network persistence objects."""
    op.drop_table("follows")
    op.drop_table("story_reactions")
    op.drop_table("customer_stories")
    op.drop_table("users")
