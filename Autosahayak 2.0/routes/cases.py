from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Case
from schemas.case import CaseCreate, CaseRead
from services.activity_service import log_activity


router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("", response_model=CaseRead)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)):
    existing = db.query(Case).filter(Case.case_number == payload.case_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Case number already exists")

    case = Case(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    log_activity(db, action="Case created", details=f"Created case {case.case_number}.", case_id=case.id)
    return case


@router.get("", response_model=list[CaseRead])
def list_cases(q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Case).order_by(Case.created_at.desc())
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Case.case_number.ilike(pattern),
                Case.client_name.ilike(pattern),
                Case.court_name.ilike(pattern),
                Case.case_type.ilike(pattern),
            )
        )
    return query.all()


@router.get("/{case_id}", response_model=CaseRead)
def get_case_details(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

