from sqlalchemy.orm import Session

from database.models import ActivityLog


def log_activity(db: Session, action: str, details: str, case_id: int | None = None) -> ActivityLog:
    entry = ActivityLog(case_id=case_id, action=action, details=details)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

