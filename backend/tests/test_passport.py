from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.passport.models import MaintenanceSchedule, Product
from app.modules.passport.router import admin_router, router
from app.modules.passport.schemas import DesignStoryUpsert, ProductCreate


def test_passport_routes_cover_public_customer_and_admin_operations() -> None:
    """The bounded context publishes every Phase 2 operation."""
    paths = {route.path for route in [*router.routes, *admin_router.routes]}

    assert router.prefix == "/api/passport"
    assert "/api/passport/by-sku/{sku}" in paths
    assert "/api/admin/products" in paths
    assert "/api/admin/products/{product_id}/certificates" in paths
    assert "/api/admin/products/{product_id}/design-story" in paths


def test_product_create_enforces_canonical_sku_and_positive_carat() -> None:
    product = ProductCreate(sku="RING-001", name="Moonlight", gem_carat=Decimal("1.25"))
    assert product.sku == "RING-001"

    with pytest.raises(ValidationError):
        ProductCreate(sku="ring 1", name="Moonlight", gem_carat=Decimal("-1"))


def test_design_story_rejects_untrusted_media_schemes() -> None:
    assert DesignStoryUpsert(media_urls=["minio://stories/example.png"]).media_urls
    with pytest.raises(ValidationError):
        DesignStoryUpsert(media_urls=["javascript:alert(1)"])


def test_maintenance_indexes_support_reminder_worker_queries() -> None:
    indexes = {index.name for index in MaintenanceSchedule.__table__.indexes}
    assert "ix_maintenance_schedules_scheduled_at" in indexes
    assert "ix_maintenance_reminder_scheduled" in indexes
    assert any(constraint.name == "uq_products_sku" or constraint.columns.keys() == ["sku"] for constraint in Product.__table__.constraints)
