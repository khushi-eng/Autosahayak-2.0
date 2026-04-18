from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class CaseBase(BaseModel):
    case_number: str
    court_name: str
    case_type: str
    parties_involved: str
    client_name: str
    client_email: EmailStr


class CaseCreate(CaseBase):
    pass


class CaseRead(CaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

