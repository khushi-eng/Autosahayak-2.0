from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents.prediction_agent import predict_outcome
from agents.research_agent import generate_research_notes
from agents.summarizer_agent import summarize_text
from database.db import get_db
from database.models import Case, ResearchNote
from schemas.ai import PredictionResponse, SummaryRequest, SummaryResponse
from schemas.research import ResearchNoteRead
from services.activity_service import log_activity


router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/research/{case_id}", response_model=ResearchNoteRead)
def create_research_notes(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    notes = generate_research_notes(case)
    research_note = ResearchNote(case_id=case_id, notes=notes)
    db.add(research_note)
    db.commit()
    db.refresh(research_note)
    log_activity(
        db,
        action="Research notes generated",
        details=f"Generated research notes for case {case.case_number}.",
        case_id=case.id,
    )
    return research_note


@router.post("/predict/{case_id}", response_model=PredictionResponse)
def predict_case_outcome(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    result = predict_outcome(case)
    log_activity(
        db,
        action="Outcome predicted",
        details=f"Generated outcome prediction for case {case.case_number}.",
        case_id=case.id,
    )
    return PredictionResponse(**result)


@router.post("/summarize", response_model=SummaryResponse)
def summarize(payload: SummaryRequest):
    return SummaryResponse(summary=summarize_text(payload.text))

