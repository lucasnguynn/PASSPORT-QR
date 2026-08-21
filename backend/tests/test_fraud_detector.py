"""Unit tests for Redis-backed fraud thresholds."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/dpp")
os.environ.setdefault("REDIS_URL", "redis://:pass@localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-at-least-thirty-two-characters")
os.environ.setdefault("ECDSA_PRIVATE_KEY_B64", "test")
os.environ.setdefault("ECDSA_PUBLIC_KEY_B64", "test")

from app.modules.qr.fraud_detector import inspect_valid_scan, record_signature_failure


@pytest.mark.asyncio
async def test_signature_failure_blocks_on_sixth_attempt() -> None:
    redis = AsyncMock()
    redis.incr.return_value = 6
    db = AsyncMock()

    await record_signature_failure("203.0.113.8", db, redis)

    redis.set.assert_awaited_once_with("qr:blocklist:203.0.113.8", "1", ex=86400)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_velocity_alert_occurs_only_at_threshold_crossing() -> None:
    redis = AsyncMock()
    redis.incr.return_value = 51
    redis.get.return_value = None
    db = AsyncMock()
    record = SimpleNamespace(id=uuid4())

    await inspect_valid_scan(record, None, "203.0.113.9", db, redis)

    db.add.assert_called_once()
    assert db.add.call_args.args[0].alert_type == "high_velocity"
