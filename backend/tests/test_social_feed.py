"""Deterministic unit tests for social feed ranking and moderation."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.modules.social.feed_algorithm import calculate_score, merge_feed_sources
from app.modules.social.moderation import auto_moderate


def story(identifier: int, score: float) -> SimpleNamespace:
    return SimpleNamespace(id=identifier, score=score)


def test_feed_score_is_deterministic() -> None:
    now = datetime(2026, 8, 21, tzinfo=UTC)
    item = SimpleNamespace(view_count=100, reaction_count=20, comment_count=5,
        published_at=now - timedelta(hours=72), media_urls=["asset"], content="x" * 200)
    assert calculate_score(item, now=now) == pytest.approx(0.058478997, rel=1e-6)


def test_feed_merge_deduplicates_then_orders_and_pages() -> None:
    result = merge_feed_sources([story(1, 1.0), story(2, 3.0)], [story(2, 3.0), story(3, 2.0)],
                                [story(4, 0.5)], page=0, limit=3)
    assert [item.id for item in result] == [2, 3, 1]


def test_moderation_rejects_short_content() -> None:
    result = auto_moderate("short", None)
    assert result.status == "flagged"
    assert result.reason == "too_short"
