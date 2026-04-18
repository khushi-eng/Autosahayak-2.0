from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from agents.drafting_agent import generate_legal_draft
from agents.summarizer_agent import summarize_text
from database.db import get_db
from database.models import Case, Document
from schemas.document import DocumentGenerateRequest, DocumentRead
from services.activity_service import log_activity
from services.document_service import save_upload_file
from services.vector_store import vector_store


router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentRead)
async def upload_document(
    case_id: int = Form(...),
    document_type: str = Form(...),
    content: str = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    file_path = await save_upload_file(file, f"case_{case_id}")
    document = Document(case_id=case_id, document_type=document_type, file_path=file_path, content=content)
    db.add(document)
    db.commit()
    db.refresh(document)

    vector_store.add_text(content, {"case_id": case_id, "document_id": document.id, "document_type": document_type})
    log_activity(
        db,
        action="Document uploaded",
        details=f"Stored {document_type} for case {case.case_number}.",
        case_id=case_id,
    )
    return document


@router.get("/{case_id}", response_model=list[DocumentRead])
def get_documents(case_id: int, db: Session = Depends(get_db)):
    return db.query(Document).filter(Document.case_id == case_id).order_by(Document.created_at.desc()).all()


@router.post("/generate", response_model=DocumentRead)
def generate_document(payload: DocumentGenerateRequest, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    draft = generate_legal_draft(payload.document_type, case)
    document = Document(case_id=payload.case_id, document_type=payload.document_type, file_path=None, content=draft)
    db.add(document)
    db.commit()
    db.refresh(document)

    vector_store.add_text(draft, {"case_id": case.id, "document_id": document.id, "document_type": payload.document_type})
    log_activity(
        db,
        action="AI draft generated",
        details=f"Generated {payload.document_type} for case {case.case_number}.",
        case_id=case.id,
    )
    return document


@router.get("/summary/{document_id}")
def summarize_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document_id": document.id, "summary": summarize_text(document.content)}

