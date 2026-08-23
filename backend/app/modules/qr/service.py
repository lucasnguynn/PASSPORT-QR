"""QR issuance, verification, revocation, and audit services."""

import asyncio
import base64
import hashlib
import io
import os
import struct
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

import qrcode
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from minio import Minio
from qrcode.constants import ERROR_CORRECT_H
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.metrics import qr_scan_total
from app.modules.passport.models import Product
from app.modules.qr.crypto import QRCrypto
from app.modules.qr.models import QRRecord, QRScanLog
from app.modules.qr.fraud_detector import inspect_valid_scan
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


COLORA_PREFIX = "https://colora.vn/secure#token="
COLORA_NONCE_SIZE = 16


def _decode_aes_key(encoded: str) -> bytes:
    """Decode either standard or URL-safe Base64 AES configuration."""
    try:
        key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("COLORA_AES_KEY_B64 is not valid Base64") from exc
    if len(key) != 32:
        raise ValueError("COLORA_AES_KEY_B64 must contain an AES-256 key")
    return key


class QRService:
    """Issue the encrypted, signed eight-layer COLORA transport envelope."""

    @staticmethod
    async def generate_colora_qr(target_url: str, product_id: UUID, db: AsyncSession) -> QRRecord:
        parsed = urlparse(target_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("target_url must be an absolute HTTP(S) URL without credentials")
        product = await db.get(Product, product_id)
        if product is None or product.status != "active":
            raise ProductNotFoundError(str(product_id))
        existing = await db.scalar(
            select(QRRecord).where(QRRecord.product_id == product_id, QRRecord.revoked_at.is_(None))
        )
        if existing is not None:
            raise ProductAlreadyHasQRError(str(product_id))

        settings = get_settings()
        try:
            key_id = int(settings.active_key_id)
        except ValueError as exc:
            raise ValueError("ACTIVE_KEY_ID must be an unsigned 32-bit integer") from exc
        if not 0 <= key_id <= 0xFFFFFFFF:
            raise ValueError("ACTIVE_KEY_ID must be an unsigned 32-bit integer")

        issued_at = datetime.fromtimestamp(int(datetime.now(UTC).timestamp()), UTC)
        nonce = os.urandom(COLORA_NONCE_SIZE)
        header = struct.pack(">IQ", key_id, int(issued_at.timestamp())) + nonce
        encrypted = AESGCM(_decode_aes_key(settings.colora_aes_key_b64)).encrypt(
            nonce, parsed.geturl().encode(), COLORA_PREFIX.encode("ascii") + header
        )
        authenticated_payload = header + encrypted
        der_signature = _load_private_key(settings.ecdsa_private_key_b64).sign(
            authenticated_payload, ec.ECDSA(hashes.SHA256())
        )
        r, s = decode_dss_signature(der_signature)
        envelope = authenticated_payload + r.to_bytes(32, "big") + s.to_bytes(32, "big")
        token = base64.urlsafe_b64encode(envelope).rstrip(b"=").decode("ascii")
        payload = COLORA_PREFIX + token
        record = QRRecord(
            product_id=product_id,
            base64url_token=token,
            token_hash=hashlib.sha256(payload.encode()).hexdigest(),
            key_id=key_id,
            aes_iv=nonce,
            target_url=parsed.geturl(),
            issued_at=issued_at,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record


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
    settings = get_settings()
    target_url = f"{settings.minio_public_url.rstrip('/')}/products/{product_id}"
    record = await QRService.generate_colora_qr(target_url, product_id, db)
    payload = COLORA_PREFIX + record.base64url_token
    record.qr_image_url = await _upload_png(product_id, _render_png(payload))
    await db.commit()
    await db.refresh(record)
    return record


async def _record_scan(
    db: AsyncSession, token_hash: str, device_fp: str, client_ip: str, result: str, product_id: UUID | None
) -> None:
    db.add(QRScanLog(product_id=product_id, token_hash=token_hash, device_fingerprint=device_fp, client_ip=client_ip, result=result))
    await db.commit()


async def log_client_scan(
    db: AsyncSession, token_hash: str, device_fp: str, client_ip: str,
    device_info: dict[str, object], result: str, user_agent: str | None,
    failure_reason: str | None = None,
) -> None:
    """Persist scanner telemetry, associating it with an issuance record when known."""
    record = await db.scalar(select(QRRecord).where(QRRecord.token_hash == token_hash))
    db.add(QRScanLog(
        product_id=record.product_id if record else None, token_hash=token_hash,
        device_fingerprint=device_fp, client_ip=client_ip, device_info=device_info,
        user_agent=user_agent, result=result, failure_reason=failure_reason,
    ))
    await db.commit()


async def verify_scan(
    token_uri: str, device_fp: str, client_ip: str, db: AsyncSession, redis: object,
    country: str | None = None,
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
        record = await db.scalar(select(QRRecord).where(QRRecord.token_hash == token_hash))
        await _record_scan(db, token_hash, device_fp, client_ip, "valid", data.product_id)
        if record is not None:
            await inspect_valid_scan(record, country, client_ip, db, redis)  # type: ignore[arg-type]
        qr_scan_total.labels(result="valid").inc()
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
    await inspect_valid_scan(record, country, client_ip, db, redis)  # type: ignore[arg-type]
    qr_scan_total.labels(result="valid").inc()
    return data
