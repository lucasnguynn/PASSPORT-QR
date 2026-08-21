"""Transactional application services for product passports."""

import asyncio
import io
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.passport.models import Certificate, DesignStory, MaintenanceSchedule, Product
from app.modules.passport.schemas import (
    CertificateCreate,
    CertificateOut,
    DesignStoryOut,
    DesignStoryUpsert,
    MaintenanceScheduleOut,
    PassportResponse,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_SIGNATURES = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")


class ProductNotFoundError(LookupError):
    """Raised when a requested product does not exist."""


class InvalidCertificateFileError(ValueError):
    """Raised when an uploaded certificate violates content controls."""


async def _product_or_error(product_id: UUID, db: AsyncSession) -> Product:
    product = await db.get(Product, product_id)
    if product is None:
        raise ProductNotFoundError(str(product_id))
    return product


async def create_product(data: ProductCreate, db: AsyncSession) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def update_product(product_id: UUID, data: ProductUpdate, db: AsyncSession) -> Product:
    product = await _product_or_error(product_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return product


async def get_passport(product_id: UUID, db: AsyncSession) -> PassportResponse:
    query = select(Product).options(
        selectinload(Product.certificates),
        selectinload(Product.design_story),
        selectinload(Product.qr_record),
        selectinload(Product.maintenance_schedules),
    ).where(Product.id == product_id, Product.status == "active")
    product = await db.scalar(query)
    if product is None:
        raise ProductNotFoundError(str(product_id))
    qr_record = product.qr_record
    return PassportResponse(
        product=ProductOut.model_validate(product),
        certificates=[CertificateOut.model_validate(item) for item in product.certificates],
        design_story=DesignStoryOut.model_validate(product.design_story) if product.design_story else None,
        maintenance_schedules=[MaintenanceScheduleOut.model_validate(item) for item in product.maintenance_schedules],
        has_qr=qr_record is not None and qr_record.revoked_at is None,
        qr_image_url=qr_record.qr_image_url if qr_record and qr_record.revoked_at is None else None,
    )


async def get_passport_by_sku(sku: str, db: AsyncSession) -> PassportResponse:
    product_id = await db.scalar(select(Product.id).where(Product.sku == sku, Product.status == "active"))
    if product_id is None:
        raise ProductNotFoundError(sku)
    return await get_passport(product_id, db)


async def add_certificate(
    product_id: UUID, data: CertificateCreate, file: UploadFile | None, db: AsyncSession, minio: object
) -> Certificate:
    await _product_or_error(product_id, db)
    document_url = data.document_url
    if file is not None:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        declared = file.content_type or ""
        is_pdf = declared == "application/pdf" and content.startswith(b"%PDF-")
        is_image = declared.startswith("image/") and content.startswith(ALLOWED_IMAGE_SIGNATURES)
        if len(content) > MAX_UPLOAD_BYTES or not (is_pdf or is_image):
            raise InvalidCertificateFileError("File must be a PDF or supported image no larger than 10 MB")
        bucket = "certificates"
        extension = (file.filename or "document").rsplit(".", 1)[-1].lower()
        object_name = f"products/{product_id}/{uuid4()}.{extension}"

        def upload() -> None:
            if not minio.bucket_exists(bucket):  # type: ignore[attr-defined]
                minio.make_bucket(bucket)  # type: ignore[attr-defined]
            minio.put_object(bucket, object_name, io.BytesIO(content), len(content), content_type=declared)  # type: ignore[attr-defined]

        await asyncio.to_thread(upload)
        document_url = f"minio://{bucket}/{object_name}"
    certificate = Certificate(product_id=product_id, **data.model_dump(exclude={"document_url"}), document_url=document_url)
    db.add(certificate)
    await db.commit()
    await db.refresh(certificate)
    return certificate


async def upsert_design_story(product_id: UUID, data: DesignStoryUpsert, db: AsyncSession) -> DesignStory:
    await _product_or_error(product_id, db)
    story = await db.scalar(select(DesignStory).where(DesignStory.product_id == product_id))
    if story is None:
        story = DesignStory(product_id=product_id, **data.model_dump())
        db.add(story)
    else:
        for field, value in data.model_dump().items():
            setattr(story, field, value)
    await db.commit()
    await db.refresh(story)
    return story


async def get_maintenance_schedule(product_id: UUID, owner_id: UUID, db: AsyncSession) -> list[MaintenanceSchedule]:
    await _product_or_error(product_id, db)
    result = await db.scalars(
        select(MaintenanceSchedule).where(
            MaintenanceSchedule.product_id == product_id, MaintenanceSchedule.owner_user_id == owner_id
        ).order_by(MaintenanceSchedule.scheduled_at)
    )
    return list(result.all())
