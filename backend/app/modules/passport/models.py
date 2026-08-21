"""Relational models owned by the product-passport context."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    """A jewelry product and the root of its passport aggregate."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gem_type: Mapped[str | None] = mapped_column(String(100))
    gem_color: Mapped[str | None] = mapped_column(String(50))
    gem_color_hex: Mapped[str | None] = mapped_column(CHAR(7))
    gem_carat: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    gem_origin: Mapped[str | None] = mapped_column(String(100))
    gem_clarity: Mapped[str | None] = mapped_column(String(50))
    silver_grade: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)
    manufactured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    certificates: Mapped[list["Certificate"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    design_story: Mapped["DesignStory | None"] = relationship(back_populates="product", cascade="all, delete-orphan")
    qr_record: Mapped["QRRecord | None"] = relationship(back_populates="product", uselist=False)
    maintenance_schedules: Mapped[list["MaintenanceSchedule"]] = relationship(cascade="all, delete-orphan")


class Certificate(Base):
    __tablename__ = "product_certificates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    cert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cert_number: Mapped[str | None] = mapped_column(String(100))
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    document_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product: Mapped[Product] = relationship(back_populates="certificates")


class DesignStory(Base):
    __tablename__ = "design_stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False)
    designer_name: Mapped[str | None] = mapped_column(String(255))
    inspiration: Mapped[str | None] = mapped_column(Text)
    craft_process: Mapped[str | None] = mapped_column(Text)
    media_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product: Mapped[Product] = relationship(back_populates="design_story")


class MaintenanceSchedule(Base):
    __tablename__ = "maintenance_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_maintenance_reminder_scheduled", "reminder_sent", "scheduled_at"),)
