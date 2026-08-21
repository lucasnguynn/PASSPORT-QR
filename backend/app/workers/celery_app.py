"""Celery worker and periodic-task configuration."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("dpp", broker=settings.redis_url, backend=settings.redis_url,
    include=["app.workers.tasks.feed_fanout", "app.workers.tasks.discovery_refresh", "app.workers.tasks.maintenance_reminder"])
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC", enable_utc=True,
    beat_schedule={
        "refresh-discovery": {"task": "feed.refresh_discovery", "schedule": 900.0},
        "maintenance-reminders": {"task": "maintenance.send_reminders", "schedule": crontab(hour=1, minute=0)},
    })
