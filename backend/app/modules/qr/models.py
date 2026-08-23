"""QR issuance and scan-audit persistence models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class QRRecord(Base):
    """An issued, independently revocable QR credential."""

    __tablename__ = "qr_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    base64url_token: Mapped[str] = mapped_column(Text())
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_id: Mapped[int] = mapped_column(Integer)
    aes_iv: Mapped[bytes] = mapped_column(LargeBinary(16))
    target_url: Mapped[str] = mapped_column(Text())
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    qr_image_url: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text())
    product: Mapped["Product"] = relationship(back_populates="qr_record")

    __table_args__ = (Index("ix_qr_active_product", "product_id", "revoked_at"),)


class QRScanLog(Base):
    """Security audit event produced for each completed verification attempt."""

    __tablename__ = "qr_scan_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(255))
    client_ip: Mapped[str] = mapped_column(String(45))
    device_info: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    user_agent: Mapped[str | None] = mapped_column(Text())
    result: Mapped[str] = mapped_column(String(32), index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FraudAlert(Base):
    """A security signal requiring staff investigation."""

    __tablename__ = "fraud_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qr_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("qr_records.id", ondelete="CASCADE"), index=True
    )
    alert_type: Mapped[str] = mapped_column(String(32), index=True)
    details: Mapped[dict[str, object]] = mapped_column(JSONB)
    client_ip: Mapped[str] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
