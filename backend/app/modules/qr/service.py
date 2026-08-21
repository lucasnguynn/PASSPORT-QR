"""QR issuance, verification, revocation, and audit services."""

import asyncio
import base64
import hashlib
import io
from datetime import UTC, datetime
from uuid import UUID

import qrcode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from minio import Minio
from qrcode.constants import ERROR_CORRECT_H
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.passport.models import Product
from app.modules.qr.crypto import QRCrypto
from app.modules.qr.models import QRRecord, QRScanLog
from app.modules.qr.schemas import PassportData


class ProductNotFoundError(LookupError):
    """Raised when no active product has the requested identifier."""


class ProductAlreadyHasQRError(ValueError):
    """Raised when an active credential already exists for a product."""


class RateLimitError(RuntimeError):
    """Raised when a device exhausts its hourly scan allowance."""


class NotFoundError(LookupError):
    """Raised when a valid token has no issuance record."""


class RevokedError(RuntimeError):
    """Raised when a credential has been revoked."""

    def __init__(self, reason: str | None) -> None:
        super().__init__("QR credential has been revoked")
        self.reason = reason or "unspecified"


def _load_private_key(encoded: str) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(base64.b64decode(encoded), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("ECDSA_PRIVATE_KEY_B64 is not an EC private key")
    return key


def _load_public_key(encoded: str) -> ec.EllipticCurvePublicKey:
    key = serialization.load_pem_public_key(base64.b64decode(encoded))
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ValueError("ECDSA_PUBLIC_KEY_B64 is not an EC public key")
    return key


def _render_png(token: str) -> bytes:
    image = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=10, border=4)
    image.add_data(token)
    image.make(fit=True)
    stream = io.BytesIO()
    image.make_image(fill_color="black", back_color="white").save(stream, format="PNG")
    return stream.getvalue()


async def _upload_png(product_id: UUID, png: bytes) -> str:
    settings = get_settings()
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket, object_name = "qr-codes", f"products/{product_id}.png"

    def upload() -> None:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(bucket, object_name, io.BytesIO(png), len(png), content_type="image/png")

    await asyncio.to_thread(upload)
    return f"{settings.minio_public_url.rstrip('/')}/{bucket}/{object_name}"


async def create_product_qr(product_id: UUID, db: AsyncSession) -> QRRecord:
    """Generate and persist a QR for an active product, rejecting duplicate active credentials."""
    product = await db.get(Product, product_id)
    if product is None or product.status != "active":
        raise ProductNotFoundError(str(product_id))
    existing = await db.scalar(
        select(QRRecord).where(QRRecord.product_id == product_id, QRRecord.revoked_at.is_(None))
    )
    if existing is not None:
        raise ProductAlreadyHasQRError(str(product_id))

    settings = get_settings()
    token = QRCrypto.generate(str(product_id), _load_private_key(settings.ecdsa_private_key_b64), settings.active_key_id)
    image_url = await _upload_png(product_id, _render_png(token))
    record = QRRecord(
        product_id=product_id,
        token=token,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        key_id=settings.active_key_id,
        qr_image_url=image_url,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def _record_scan(
    db: AsyncSession, token_hash: str, device_fp: str, client_ip: str, result: str, product_id: UUID | None
) -> None:
    db.add(QRScanLog(product_id=product_id, token_hash=token_hash, device_fingerprint=device_fp, client_ip=client_ip, result=result))
    await db.commit()


async def verify_scan(
    token_uri: str, device_fp: str, client_ip: str, db: AsyncSession, redis: object
) -> PassportData:
    """Run rate limiting, cryptographic verification, persistence checks, caching, and audit logging."""
    rate_key = f"qr:rate:{device_fp}"
    attempts = await redis.incr(rate_key)  # type: ignore[attr-defined]
    if attempts == 1:
        await redis.expire(rate_key, 3600)  # type: ignore[attr-defined]
    if attempts > 20:
        raise RateLimitError("Device scan limit exceeded")

    token_hash = hashlib.sha256(token_uri.encode()).hexdigest()
    cache_key = f"qr:cache:{token_hash}"
    cached = await redis.get(cache_key)  # type: ignore[attr-defined]
    if cached:
        data = PassportData.model_validate_json(cached)
        await _record_scan(db, token_hash, device_fp, client_ip, "valid", data.product_id)
        return data

    settings = get_settings()
    verified = QRCrypto.verify(token_uri, {settings.active_key_id: _load_public_key(settings.ecdsa_public_key_b64)})
    record = await db.scalar(select(QRRecord).where(QRRecord.token_hash == token_hash))
    if record is None:
        raise NotFoundError(token_hash)
    if record.revoked_at is not None:
        raise RevokedError(record.revoke_reason)
    product = await db.get(Product, UUID(verified["product_uuid"]))
    if product is None or product.status != "active":
        raise NotFoundError(str(record.product_id))

    data = PassportData(product_id=product.id, name=product.name, verified_at=datetime.now(UTC))
    await redis.set(cache_key, data.model_dump_json(), ex=300)  # type: ignore[attr-defined]
    await _record_scan(db, token_hash, device_fp, client_ip, "valid", product.id)
    return data
