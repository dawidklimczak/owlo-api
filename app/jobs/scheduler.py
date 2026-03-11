"""
Background scheduler — runs as a standalone process (Procfile: worker).
Checks topics due for update every hour.
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.topic import Topic, TopicStatus
from app.services.topic_checker import check_topic


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def run_due_checks() -> None:
    """Find all topics due for checking and process them."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due_topics = (
            db.query(Topic)
            .filter(
                Topic.status == TopicStatus.active,
                Topic.next_check_at <= now,
            )
            .all()
        )

        if not due_topics:
            logger.info("No topics due for checking")
            return

        logger.info("Found %d topics due for checking", len(due_topics))

        for topic in due_topics:
            try:
                logger.info("Checking topic '%s' (id=%s)", topic.title, topic.id)
                new_facts = await check_topic(topic, db)
                logger.info("Topic '%s' — %d new fact(s)", topic.title, new_facts)
            except Exception as e:
                logger.error("Error checking topic %s: %s", topic.id, e, exc_info=True)
                db.rollback()

    finally:
        db.close()


def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_due_checks,
        trigger="interval",
        hours=1,
        id="check_topics",
        next_run_time=datetime.now(timezone.utc),  # Run immediately on startup
        misfire_grace_time=300,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        loop.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scheduler.start()
    logger.info("Scheduler started — checking topics every hour")

    try:
        loop.run_forever()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
