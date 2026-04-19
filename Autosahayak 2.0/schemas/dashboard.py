from datetime import datetime

from pydantic import BaseModel


class ActivityItem(BaseModel):
    action: str
    details: str
    created_at: datetime


class HearingReminder(BaseModel):
    id: int
    case_number: str
    hearing_date: datetime
    court_name: str
    next_action: str


class DashboardResponse(BaseModel):
    total_cases: int
    upcoming_hearings: int
    deadlines: int
    recent_activity: list[ActivityItem]
    hearing_reminders: list[HearingReminder] = []

