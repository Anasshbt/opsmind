"""
Background worker — expires stale lab sessions.
Runs as a Celery beat task every 60 seconds.

Can also be run standalone:
  python -m app.workers.session_cleanup
"""
import asyncio

import structlog
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

celery_app = Celery("opsmind", broker=str(settings.REDIS_URL))
celery_app.conf.beat_schedule = {
    "expire-lab-sessions": {
        "task": "app.workers.session_cleanup.expire_sessions",
        "schedule": 60.0,  # every 60 seconds
    },
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="app.workers.session_cleanup.expire_sessions")
def expire_sessions() -> int:
    return asyncio.run(_expire_async())


async def _expire_async() -> int:
    from app.db.session import AsyncSessionLocal
    from app.services.lab.session_manager import SessionManager
    from redis.asyncio import from_url

    async with AsyncSessionLocal() as db:
        redis = from_url(str(settings.REDIS_URL), decode_responses=True)
        mgr = SessionManager(db=db, redis=redis)
        count = await mgr.expire_stale_sessions()
        await db.commit()
        await redis.aclose()
        return count


if __name__ == "__main__":
    count = asyncio.run(_expire_async())
    logger.info("manual_cleanup_done", expired=count)
