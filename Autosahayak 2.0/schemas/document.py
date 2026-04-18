from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    case_id: int
    document_type: str
    content: str


class DocumentGenerateRequest(BaseModel):
    case_id: int
    document_type: str


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    document_type: str
    file_path: str | None
    content: str
    created_at: datetime

