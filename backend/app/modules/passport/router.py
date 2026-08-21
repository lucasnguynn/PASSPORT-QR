"""Public, customer, and administrator passport HTTP endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile, status
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.rate_limit import limiter
from app.core.security import require_admin, require_customer
from app.modules.passport.models import MaintenanceSchedule, Product
from app.modules.social.models import User
from app.modules.passport.schemas import (
    CertificateCreate,
    CertificateOut,
    DesignStoryOut,
    DesignStoryUpsert,
    MaintenanceScheduleCreate,
    MaintenanceScheduleOut,
    PassportResponse,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.modules.passport.service import (
    InvalidCertificateFileError,
    ProductNotFoundError,
    add_certificate,
    create_product,
    get_passport,
    get_passport_by_sku,
    update_product,
    upsert_design_story,
)

router = APIRouter(prefix="/api/passport", tags=["passport"])
admin_router = APIRouter(prefix="/api/admin", tags=["passport-admin"])


def get_minio() -> Minio:
    """Build the S3-compatible client from environment-backed settings."""
    settings = get_settings()
    return Minio(settings.minio_endpoint, settings.minio_access_key, settings.minio_secret_key, secure=settings.minio_secure)


@router.get("/{product_id}", response_model=PassportResponse)
@limiter.limit("200/minute")
async def passport_by_id(request: Request, product_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]) -> PassportResponse:
    """Return the public passport for an active product identifier."""
    try:
        return await get_passport(product_id, db)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc


@router.get("/by-sku/{sku}", response_model=PassportResponse)
@limiter.limit("200/minute")
async def passport_by_sku(request: Request, sku: str, db: Annotated[AsyncSession, Depends(get_session)]) -> PassportResponse:
    """Return the public passport matching an active product SKU."""
    try:
        return await get_passport_by_sku(sku, db)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc


@admin_router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("500/minute")
async def create_product_endpoint(request: Request, data: ProductCreate, db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[User, Depends(require_admin)]) -> Product:
    """Create a product passport root (administrator only)."""
    return await create_product(data, db)


@admin_router.patch("/products/{product_id}", response_model=ProductOut)
@limiter.limit("500/minute")
async def update_product_endpoint(request: Request, product_id: UUID, data: ProductUpdate, db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[User, Depends(require_admin)]) -> Product:
    """Partially update product attributes (administrator only)."""
    try:
        return await update_product(product_id, data, db)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc


@admin_router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("500/minute")
async def archive_product(request: Request, product_id: UUID, db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[User, Depends(require_admin)]) -> None:
    """Soft-delete a product by moving it to archived status (administrator only)."""
    try:
        await update_product(product_id, ProductUpdate(status="archived"), db)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc


@admin_router.post("/products/{product_id}/certificates", response_model=CertificateOut, status_code=201)
@limiter.limit("500/minute")
async def create_certificate(request: Request, product_id: UUID, data: Annotated[CertificateCreate, Body()], db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[User, Depends(require_admin)], minio: Annotated[Minio, Depends(get_minio)], file: Annotated[UploadFile | None, File()] = None) -> object:
    """Attach certificate metadata and an optional validated document (administrator only)."""
    try:
        return await add_certificate(product_id, data, file, db, minio)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except InvalidCertificateFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc


@admin_router.put("/products/{product_id}/design-story", response_model=DesignStoryOut)
@limiter.limit("500/minute")
async def put_design_story(request: Request, product_id: UUID, data: DesignStoryUpsert, db: Annotated[AsyncSession, Depends(get_session)], _admin: Annotated[User, Depends(require_admin)]) -> object:
    """Create or replace a product's design narrative (administrator only)."""
    try:
        return await upsert_design_story(product_id, data, db)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc


@router.post("/{product_id}/maintenance", response_model=MaintenanceScheduleOut, status_code=201)
@limiter.limit("200/minute")
async def schedule_maintenance(request: Request, product_id: UUID, data: MaintenanceScheduleCreate, db: Annotated[AsyncSession, Depends(get_session)], customer: Annotated[User, Depends(require_customer)]) -> MaintenanceSchedule:
    """Schedule product care for the authenticated customer."""
    owner_id = customer.id
    if await db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    schedule = MaintenanceSchedule(product_id=product_id, owner_user_id=owner_id, **data.model_dump())
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.patch("/{product_id}/maintenance/{schedule_id}/complete", response_model=MaintenanceScheduleOut)
@limiter.limit("200/minute")
async def complete_maintenance(request: Request, product_id: UUID, schedule_id: UUID, db: Annotated[AsyncSession, Depends(get_session)], customer: Annotated[User, Depends(require_customer)]) -> MaintenanceSchedule:
    """Mark the authenticated customer's maintenance appointment complete."""
    schedule = await db.get(MaintenanceSchedule, schedule_id)
    if schedule is None or schedule.product_id != product_id or schedule.owner_user_id != customer.id:
        raise HTTPException(status_code=404, detail="Maintenance schedule not found")
    schedule.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(schedule)
    return schedule

# Starlette resolves in declaration order, so the literal by-SKU route must precede /{product_id}.
_product_route = next(route for route in router.routes if route.path == "/api/passport/{product_id}")
router.routes.remove(_product_route)
router.routes.append(_product_route)
