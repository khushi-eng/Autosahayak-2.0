from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Case, Deadline
from schemas.deadline import DeadlineCreate, DeadlineRead
from services.activity_service import log_activity
from services.reminder_service import send_deadline_reminder


router = APIRouter(prefix="/deadlines", tags=["Deadlines"])


@router.post("", response_model=DeadlineRead)
def add_deadline(payload: DeadlineCreate, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    deadline = Deadline(**payload.model_dump())
    db.add(deadline)
    db.commit()
    db.refresh(deadline)
    log_activity(
        db,
        action="Deadline added",
        details=f"Added deadline '{deadline.title}' for case {case.case_number}.",
        case_id=case.id,
    )
    return deadline


@router.get("/{case_id}", response_model=list[DeadlineRead])
def list_deadlines(case_id: int, db: Session = Depends(get_db)):
    return db.query(Deadline).filter(Deadline.case_id == case_id).order_by(Deadline.deadline.asc()).all()


@router.post("/send-reminder/{deadline_id}")
def send_reminder(deadline_id: int, db: Session = Depends(get_db)):
    deadline = db.query(Deadline).filter(Deadline.id == deadline_id).first()
    if not deadline:
        raise HTTPException(status_code=404, detail="Deadline not found")
    return send_deadline_reminder(db, deadline_id)

