from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResearchNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    notes: str
    created_at: datetime

