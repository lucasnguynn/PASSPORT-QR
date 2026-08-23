"""HTTP endpoints for QR verification and credential administration."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.metrics import qr_scan_total
from app.core.rate_limit import limiter
from app.core.redis_client import get_redis
from app.core.security import require_admin
from app.modules.qr.crypto import ChecksumError, InvalidSignatureError, SchemeError
from app.modules.qr.fraud_detector import record_signature_failure
from app.modules.qr.models import QRRecord, QRScanLog
from app.modules.qr.schemas import (
    PaginatedScanLogs,
    PassportData,
    ColoraQRGenerationRequest,
    QRGenerationResponse,
    RevokeRequest,
    RevokeResponse,
    ScanLogResponse,
    ScanTelemetryRequest,
    ScanTelemetryResponse,
    VerifyQRRequest,
)
from app.modules.qr.service import (
    NotFoundError,
    ProductAlreadyHasQRError,
    ProductNotFoundError,
    RateLimitError,
    RevokedError,
    create_product_qr,
    log_client_scan,
    QRService,
    verify_scan,
)

router = APIRouter(tags=["qr"])


def _generation_response(record: QRRecord) -> QRGenerationResponse:
    return QRGenerationResponse(
        payload=f"https://colora.vn/secure#token={record.base64url_token}",
        token_hash=record.token_hash,
        product_id=record.product_id,
        issued_at=record.issued_at,
    )


@router.post("/api/qr/generate", response_model=QRGenerationResponse, status_code=201)
@limiter.limit("500/minute")
async def generate_colora_qr(
    request: Request,
    body: ColoraQRGenerationRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[object, Depends(require_admin)],
) -> QRGenerationResponse:
    """Generate and persist an eight-layer COLORA payload (administrator only)."""
    try:
        return _generation_response(
            await QRService.generate_colora_qr(body.target_url, body.product_id, db)
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Active product not found") from exc
    except ProductAlreadyHasQRError as exc:
        raise HTTPException(status_code=409, detail="Product already has an active QR") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/qr/log-scan", response_model=ScanTelemetryResponse, status_code=202)
@limiter.limit("120/minute")
async def log_scan(
    request: Request,
    body: ScanTelemetryRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ScanTelemetryResponse:
    """Accept best-effort public telemetry from a client-side verified scan."""
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    device_fp = body.device_fingerprint or str(body.device_info.get("userAgent", "unknown"))[:255]
    await log_client_scan(
        db, body.token_hash, device_fp, client_ip, body.device_info,
        body.status, request.headers.get("user-agent"), body.failure_reason,
    )
    qr_scan_total.labels(result=body.status).inc()
    return ScanTelemetryResponse()


@router.post("/api/qr/verify", response_model=PassportData)
@limiter.limit("60/minute")
async def verify_qr(
    request: Request,
    body: VerifyQRRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PassportData | JSONResponse:
    """Authenticate a public QR scan and return its Digital Product Passport."""
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    try:
        country = request.headers.get("CF-IPCountry") or request.headers.get("X-Country-Code")
        return await verify_scan(body.token_uri, body.device_fingerprint, client_ip, db, redis, country)
    except SchemeError as exc:
        qr_scan_total.labels(result="invalid").inc()
        return JSONResponse(status_code=400, content={"status": "invalid_scheme", "message": str(exc)})
    except ChecksumError as exc:
        qr_scan_total.labels(result="invalid").inc()
        return JSONResponse(status_code=400, content={"status": "checksum_failed", "message": str(exc)})
    except InvalidSignatureError as exc:
        await record_signature_failure(client_ip, db, redis)
        qr_scan_total.labels(result="invalid").inc()
        return JSONResponse(status_code=400, content={"status": "invalid_signature", "message": str(exc)})
    except NotFoundError:
        return JSONResponse(status_code=404, content={"status": "not_found"})
    except RevokedError as exc:
        qr_scan_total.labels(result="revoked").inc()
        return JSONResponse(status_code=410, content={"status": "revoked", "revoke_reason": exc.reason})
    except RateLimitError:
        return JSONResponse(status_code=429, content={"status": "rate_limited"})


@router.post("/api/admin/qr/generate/{product_id}", response_model=QRGenerationResponse, status_code=201)
@limiter.limit("500/minute")
async def generate_qr(
    request: Request,
    product_id: UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[object, Depends(require_admin)],
) -> QRGenerationResponse:
    """Issue a signed QR credential for an active product (administrator only)."""
    try:
        return _generation_response(await create_product_qr(product_id, db))
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Active product not found") from exc
    except ProductAlreadyHasQRError as exc:
        raise HTTPException(status_code=409, detail="Product already has an active QR") from exc


@router.post("/api/admin/qr/revoke/{product_id}", response_model=RevokeResponse)
@limiter.limit("500/minute")
async def revoke_qr(
    request: Request,
    product_id: UUID,
    body: RevokeRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[object, Depends(require_admin)],
) -> RevokeResponse:
    """Revoke a product's current credential and invalidate future scans."""
    record = await db.scalar(select(QRRecord).where(QRRecord.product_id == product_id, QRRecord.revoked_at.is_(None)))
    if record is None:
        raise HTTPException(status_code=404, detail="Active QR credential not found")
    record.revoked_at = datetime.now(UTC)
    record.revoke_reason = body.reason
    await db.commit()
    return RevokeResponse(revoked_at=record.revoked_at)


@router.get("/api/admin/qr/scan-logs", response_model=PaginatedScanLogs)
@limiter.limit("500/minute")
async def scan_logs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[object, Depends(require_admin)],
    product_id: UUID | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    result: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedScanLogs:
    """List filtered QR scan audit events for fraud investigation."""
    query = select(QRScanLog)
    if product_id is not None:
        query = query.where(QRScanLog.product_id == product_id)
    if from_ is not None:
        query = query.where(QRScanLog.scanned_at >= from_)
    if to is not None:
        query = query.where(QRScanLog.scanned_at <= to)
    if result is not None:
        query = query.where(QRScanLog.result == result)
    rows = (await db.scalars(query.order_by(QRScanLog.scanned_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return PaginatedScanLogs(items=[ScanLogResponse.model_validate(row) for row in rows], page=page, page_size=page_size)
