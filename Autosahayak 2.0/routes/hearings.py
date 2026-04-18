from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Case, Hearing
from schemas.hearing import HearingCreate, HearingRead
from services.activity_service import log_activity


router = APIRouter(prefix="/hearings", tags=["Hearings"])


@router.post("", response_model=HearingRead)
def add_hearing(payload: HearingCreate, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    hearing = Hearing(**payload.model_dump())
    db.add(hearing)
    db.commit()
    db.refresh(hearing)
    log_activity(
        db,
        action="Hearing added",
        details=f"Hearing scheduled for case {case.case_number} on {hearing.hearing_date.isoformat()}.",
        case_id=case.id,
    )
    return hearing


@router.get("/{case_id}", response_model=list[HearingRead])
def list_hearings(case_id: int, db: Session = Depends(get_db)):
    return db.query(Hearing).filter(Hearing.case_id == case_id).order_by(Hearing.hearing_date.asc()).all()

