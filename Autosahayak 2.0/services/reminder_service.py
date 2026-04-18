import asyncio
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from agents.scheduler_agent import detect_due_deadlines, trigger_reminder
from database.db import SessionLocal
from database.models import Deadline
from services.activity_service import log_activity
from utils.logging_config import get_logger


logger = get_logger(__name__)


def send_deadline_reminder(db: Session, deadline_id: int) -> dict[str, str]:
    deadline = db.query(Deadline).filter(Deadline.id == deadline_id).first()
    if not deadline:
        raise ValueError("Deadline not found")

    message = trigger_reminder(deadline.title, deadline.case.client_email, deadline.deadline)
    deadline.reminder_sent = True
    db.commit()
    log_activity(
        db,
        action="Reminder sent",
        details=f"Reminder issued for deadline '{deadline.title}' to {deadline.case.client_email}.",
        case_id=deadline.case_id,
    )
    logger.info(message)
    return {"message": message}


async def reminder_worker(stop_event: asyncio.Event, poll_interval: int = 20) -> None:
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            window_end = now + timedelta(hours=24)
            pending = (
                db.query(Deadline)
                .filter(Deadline.reminder_sent.is_(False), Deadline.deadline >= now, Deadline.deadline <= window_end)
                .all()
            )
            due = detect_due_deadlines(pending)
            for deadline in due:
                send_deadline_reminder(db, deadline.id)
        except Exception as exc:  # pragma: no cover
            logger.exception("Reminder worker failed: %s", exc)
        finally:
            db.close()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            continue

