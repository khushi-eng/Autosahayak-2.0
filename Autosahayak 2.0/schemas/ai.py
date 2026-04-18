from pydantic import BaseModel


class PredictionResponse(BaseModel):
    success_probability: float
    risk_analysis: str
    summary: str


class SummaryRequest(BaseModel):
    text: str


class SummaryResponse(BaseModel):
    summary: str

