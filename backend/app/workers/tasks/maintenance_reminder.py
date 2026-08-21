"""Upcoming product-care reminder task."""
import asyncio
from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import select

from app.core.database import session_factory
from app.modules.passport.models import MaintenanceSchedule
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="maintenance.send_reminders")
def send_maintenance_reminders() -> int:
    """Record reminders for incomplete maintenance due in the next seven days."""
    return asyncio.run(_send_maintenance_reminders())


async def _send_maintenance_reminders() -> int:
    now = datetime.now(UTC)
    async with session_factory() as db:
        schedules = list(await db.scalars(select(MaintenanceSchedule).where(MaintenanceSchedule.reminder_sent.is_(False),
            MaintenanceSchedule.completed_at.is_(None), MaintenanceSchedule.scheduled_at.between(now, now + timedelta(days=7)))))
        for schedule in schedules:
            logger.info("maintenance reminder queued", extra={"schedule_id": str(schedule.id), "owner_user_id": str(schedule.owner_user_id)})
            schedule.reminder_sent = True
        await db.commit()
    return len(schedules)
