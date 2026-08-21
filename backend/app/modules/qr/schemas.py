"""Validated QR API request and response contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VerifyQRRequest(BaseModel):
    token_uri: str = Field(min_length=1, max_length=512)
    device_fingerprint: str = Field(min_length=1, max_length=255)


class PassportData(BaseModel):
    product_id: UUID
    name: str
    description: str | None = None
    verified_at: datetime


class QRGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    qr_image_url: str
    token: str
    product_id: UUID


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RevokeResponse(BaseModel):
    revoked_at: datetime


class ScanLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID | None
    result: str
    device_fingerprint: str
    client_ip: str
    scanned_at: datetime


class PaginatedScanLogs(BaseModel):
    items: list[ScanLogResponse]
    page: int
    page_size: int
