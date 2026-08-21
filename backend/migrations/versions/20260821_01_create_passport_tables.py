"""create passport tables

Revision ID: 20260821_01
Revises:
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260821_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create product-passport aggregate tables and query indexes."""
    op.create_table("products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("sku", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("gem_type", sa.String(100)), sa.Column("gem_color", sa.String(50)),
        sa.Column("gem_color_hex", sa.CHAR(7)), sa.Column("gem_carat", sa.Numeric(8, 4)), sa.Column("gem_origin", sa.String(100)),
        sa.Column("gem_clarity", sa.String(50)), sa.Column("silver_grade", sa.String(20)), sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("manufactured_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("sku"))
    op.create_index("ix_products_status", "products", ["status"])
    op.create_table("product_certificates", sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cert_type", sa.String(20), nullable=False), sa.Column("cert_number", sa.String(100)), sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("issued_at", sa.Date()), sa.Column("expires_at", sa.Date()), sa.Column("document_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_table("design_stories", sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("designer_name", sa.String(255)), sa.Column("inspiration", sa.Text()), sa.Column("craft_process", sa.Text()),
        sa.Column("media_urls", postgresql.JSONB(), server_default="[]", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("product_id"))
    op.create_table("maintenance_schedules", sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True)), sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminder_sent", sa.Boolean(), server_default=sa.false(), nullable=False), sa.Column("notes", sa.Text()), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.ForeignKeyConstraint(["product_id"], ["products.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_maintenance_schedules_scheduled_at", "maintenance_schedules", ["scheduled_at"])
    op.create_index("ix_maintenance_schedules_reminder_sent", "maintenance_schedules", ["reminder_sent"])
    op.create_index("ix_maintenance_reminder_scheduled", "maintenance_schedules", ["reminder_sent", "scheduled_at"])


def downgrade() -> None:
    """Drop product-passport tables in dependency order."""
    op.drop_table("maintenance_schedules")
    op.drop_table("design_stories")
    op.drop_table("product_certificates")
    op.drop_index("ix_products_status", table_name="products")
    op.drop_table("products")
