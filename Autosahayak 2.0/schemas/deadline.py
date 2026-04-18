from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeadlineCreate(BaseModel):
    case_id: int
    title: str
    deadline: datetime


class DeadlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    title: str
    deadline: datetime
    reminder_sent: bool

