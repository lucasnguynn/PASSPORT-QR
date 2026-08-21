"""Create QR fraud alerts.

Revision ID: 20260821_03
Revises: 20260821_02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_03"
down_revision: str | None = "20260821_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add persistent fraud investigation records."""
    op.create_table(
        "fraud_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("qr_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("client_ip", postgresql.INET(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["qr_record_id"], ["qr_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fraud_alerts_alert_type", "fraud_alerts", ["alert_type"])
    op.create_index("ix_fraud_alerts_qr_record_id", "fraud_alerts", ["qr_record_id"])


def downgrade() -> None:
    """Remove persistent fraud investigation records."""
    op.drop_index("ix_fraud_alerts_qr_record_id", table_name="fraud_alerts")
    op.drop_index("ix_fraud_alerts_alert_type", table_name="fraud_alerts")
    op.drop_table("fraud_alerts")
