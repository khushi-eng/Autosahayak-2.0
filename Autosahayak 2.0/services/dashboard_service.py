from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import ActivityLog, Case, Deadline, Hearing
from schemas.dashboard import ActivityItem, DashboardResponse


def get_dashboard_data(db: Session) -> DashboardResponse:
    now = datetime.now(timezone.utc)
    hearing_window = now + timedelta(days=14)

    total_cases = db.query(func.count(Case.id)).scalar() or 0
    upcoming_hearings = (
        db.query(func.count(Hearing.id))
        .filter(Hearing.hearing_date >= now, Hearing.hearing_date <= hearing_window)
        .scalar()
        or 0
    )
    deadlines = (
        db.query(func.count(Deadline.id))
        .filter(Deadline.deadline >= now, Deadline.deadline <= hearing_window)
        .scalar()
        or 0
    )
    recent_activity_rows = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(8).all()

    recent_activity = [
        ActivityItem(action=row.action, details=row.details, created_at=row.created_at)
        for row in recent_activity_rows
    ]

    return DashboardResponse(
        total_cases=total_cases,
        upcoming_hearings=upcoming_hearings,
        deadlines=deadlines,
        recent_activity=recent_activity,
    )

