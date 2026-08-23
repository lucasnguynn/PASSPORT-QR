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
    """Add QR issuance, scan telemetry, and fraud investigation records."""
    op.create_table(
        "qr_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base64url_token", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("aes_iv", sa.LargeBinary(16), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qr_image_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.Text()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_qr_records_product_id", "qr_records", ["product_id"])
    op.create_index("ix_qr_records_token_hash", "qr_records", ["token_hash"], unique=True)
    op.create_index("ix_qr_records_issued_at", "qr_records", ["issued_at"])
    op.create_index("ix_qr_active_product", "qr_records", ["product_id", "revoked_at"])
    op.create_table(
        "qr_scan_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("device_fingerprint", sa.String(255), nullable=False),
        sa.Column("client_ip", sa.String(45), nullable=False),
        sa.Column("device_info", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("user_agent", sa.Text()),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("failure_reason", sa.String(255)),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qr_scan_logs_product_id", "qr_scan_logs", ["product_id"])
    op.create_index("ix_qr_scan_logs_token_hash", "qr_scan_logs", ["token_hash"])
    op.create_index("ix_qr_scan_logs_result", "qr_scan_logs", ["result"])
    op.create_index("ix_qr_scan_logs_scanned_at", "qr_scan_logs", ["scanned_at"])
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
    op.drop_table("qr_scan_logs")
    op.drop_table("qr_records")
