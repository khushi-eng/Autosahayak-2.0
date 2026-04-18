from datetime import datetime

from pydantic import BaseModel


class ActivityItem(BaseModel):
    action: str
    details: str
    created_at: datetime


class DashboardResponse(BaseModel):
    total_cases: int
    upcoming_hearings: int
    deadlines: int
    recent_activity: list[ActivityItem]

