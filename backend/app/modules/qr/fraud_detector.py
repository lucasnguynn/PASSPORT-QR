"""Redis-assisted QR fraud pattern detection."""

import json
import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import qr_fraud_alerts_total
from app.modules.qr.models import FraudAlert, QRRecord

logger = logging.getLogger(__name__)


async def _increment_window(redis: Redis, key: str, ttl: int) -> int:
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, ttl)
    return count


async def _raise_alert(
    db: AsyncSession,
    record: QRRecord | None,
    alert_type: str,
    details: dict[str, object],
    client_ip: str,
) -> None:
    db.add(
        FraudAlert(
            qr_record_id=record.id if record else None,
            alert_type=alert_type,
            details=details,
            client_ip=client_ip,
        )
    )
    await db.commit()
    qr_fraud_alerts_total.labels(alert_type=alert_type).inc()
    logger.warning("QR fraud alert type=%s qr_record_id=%s ip=%s", alert_type, record.id if record else None, client_ip)


async def inspect_valid_scan(
    record: QRRecord, country: str | None, client_ip: str, db: AsyncSession, redis: Redis
) -> None:
    """Detect credential velocity and implausible cross-country movement."""
    velocity_key = f"qr:velocity:{record.id}"
    count = await _increment_window(redis, velocity_key, 3600)
    if count == 51:
        await _raise_alert(db, record, "high_velocity", {"scans_in_hour": count}, client_ip)

    if not country:
        return
    now = datetime.now(UTC)
    location_key = f"qr:location:{record.id}"
    previous = await redis.get(location_key)
    if previous:
        prior = json.loads(previous)
        prior_time = datetime.fromisoformat(prior["timestamp"])
        if prior["country"] != country and (now - prior_time).total_seconds() <= 1800:
            await _raise_alert(
                db,
                record,
                "geo_anomaly",
                {"previous_country": prior["country"], "country": country, "window_seconds": 1800},
                client_ip,
            )
    await redis.set(location_key, json.dumps({"country": country, "timestamp": now.isoformat()}), ex=1800)


async def record_signature_failure(
    client_ip: str, db: AsyncSession, redis: Redis, record: QRRecord | None = None
) -> None:
    """Block an IP for 24 hours after more than five bad signatures per hour."""
    count = await _increment_window(redis, f"qr:sig_fail:{client_ip}", 3600)
    if count == 6:
        await redis.set(f"qr:blocklist:{client_ip}", "1", ex=86400)
        await _raise_alert(db, record, "sig_fail_rate", {"failures_in_hour": count}, client_ip)
