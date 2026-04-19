from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HearingCreate(BaseModel):
    case_id: int
    hearing_date: datetime
    notes: str
    next_action: str


class HearingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    hearing_date: datetime
    notes: str
    next_action: str
    reminder_sent: bool = False

