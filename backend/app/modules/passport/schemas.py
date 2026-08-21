"""Validated passport API request and response contracts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _media_url(value: str) -> str:
    if value.startswith("minio://") or value.startswith("https://") or value.startswith("http://"):
        return value
    raise ValueError("media URL must be HTTP(S) or a minio:// path")


MediaUrl = Annotated[str, AfterValidator(_media_url)]


class ProductCreate(BaseModel):
    sku: str = Field(min_length=3, max_length=50, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
    gem_type: str | None = Field(default=None, max_length=100)
    gem_color: str | None = Field(default=None, max_length=50)
    gem_color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    gem_carat: Decimal | None = Field(default=None, gt=0)
    gem_origin: str | None = Field(default=None, max_length=100)
    gem_clarity: str | None = Field(default=None, max_length=50)
    silver_grade: str | None = Field(default=None, max_length=20)
    manufactured_at: datetime | None = None


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Z0-9-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gem_type: str | None = Field(default=None, max_length=100)
    gem_color: str | None = Field(default=None, max_length=50)
    gem_color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    gem_carat: Decimal | None = Field(default=None, gt=0)
    gem_origin: str | None = Field(default=None, max_length=100)
    gem_clarity: str | None = Field(default=None, max_length=50)
    silver_grade: str | None = Field(default=None, max_length=20)
    manufactured_at: datetime | None = None
    status: Literal["active", "archived"] | None = None


class CertificateCreate(BaseModel):
    cert_type: Literal["GIA", "AGL", "safety", "internal"]
    cert_number: str | None = Field(default=None, max_length=100)
    issuer: str = Field(min_length=1, max_length=255)
    issued_at: date | None = None
    expires_at: date | None = None
    document_url: str | None = None


class DesignStoryUpsert(BaseModel):
    designer_name: str | None = Field(default=None, max_length=255)
    inspiration: str | None = None
    craft_process: str | None = None
    media_urls: list[MediaUrl] = Field(default_factory=list, max_length=10)


class MaintenanceScheduleCreate(BaseModel):
    scheduled_at: datetime
    notes: str | None = None


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductOut(OrmModel):
    id: UUID
    sku: str
    name: str
    gem_type: str | None
    gem_color: str | None
    gem_color_hex: str | None
    gem_carat: Decimal | None
    gem_origin: str | None
    gem_clarity: str | None
    silver_grade: str | None
    status: str
    manufactured_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CertificateOut(OrmModel):
    id: UUID
    product_id: UUID
    cert_type: str
    cert_number: str | None
    issuer: str
    issued_at: date | None
    expires_at: date | None
    document_url: str | None
    created_at: datetime


class DesignStoryOut(OrmModel):
    id: UUID
    product_id: UUID
    designer_name: str | None
    inspiration: str | None
    craft_process: str | None
    media_urls: list[str]
    created_at: datetime


class MaintenanceScheduleOut(OrmModel):
    id: UUID
    product_id: UUID
    owner_user_id: UUID | None
    scheduled_at: datetime
    reminder_sent: bool
    notes: str | None
    completed_at: datetime | None
    created_at: datetime


class PassportResponse(BaseModel):
    product: ProductOut
    certificates: list[CertificateOut]
    design_story: DesignStoryOut | None
    maintenance_schedules: list[MaintenanceScheduleOut]
    has_qr: bool
    qr_image_url: str | None
