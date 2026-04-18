import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from agents.drafting_agent import generate_legal_draft
from agents.prediction_agent import predict_outcome
from agents.research_agent import generate_research_notes
from agents.summarizer_agent import summarize_text
from database.db import Base, SessionLocal, engine, get_db
from database.models import Case, Deadline, Document, Hearing, ResearchNote
from routes.ai import router as ai_router
from routes.cases import router as cases_router
from routes.deadlines import router as deadlines_router
from routes.documents import router as documents_router
from routes.hearings import router as hearings_router
from services.activity_service import log_activity
from services.dashboard_service import get_dashboard_data
from services.demo_seed_service import seed_demo_data_if_empty
from services.reminder_service import reminder_worker
from services.vector_store import vector_store
from utils.logging_config import configure_logging, get_logger


configure_logging()
logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_db = SessionLocal()
    try:
        seeded = seed_demo_data_if_empty(seed_db)
        if seeded:
            logger.info("Loaded demo data for Autosahayak 2.0")
    finally:
        seed_db.close()
    stop_event = asyncio.Event()
    reminder_task = asyncio.create_task(reminder_worker(stop_event))
    app.state.stop_event = stop_event
    app.state.reminder_task = reminder_task
    logger.info("Autosahayak 2.0 started")
    yield
    stop_event.set()
    await reminder_task
    logger.info("Autosahayak 2.0 stopped")


app = FastAPI(
    title="Autosahayak 2.0",
    description="AI-powered legal workflow agent for court case management.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(cases_router)
app.include_router(documents_router)
app.include_router(hearings_router)
app.include_router(deadlines_router)
app.include_router(ai_router)


def _redirect_to_case_detail(case_id: int, **params: str | int | float) -> RedirectResponse:
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    url = f"/ui/cases/{case_id}"
    if clean_params:
        url = f"{url}?{urlencode(clean_params)}"
    return RedirectResponse(url=url, status_code=303)


@app.get("/dashboard")
def dashboard_api(db: Session = Depends(get_db)):
    return get_dashboard_data(db)


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    data = get_dashboard_data(db)
    cases = db.query(Case).order_by(Case.created_at.desc()).limit(5).all()
    return templates.TemplateResponse(
        name="dashboard.html",
        context={"request": request, "dashboard": data, "cases": cases},
    )


@app.get("/ui/cases", response_class=HTMLResponse)
def cases_page(request: Request, q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Case).order_by(Case.created_at.desc())
    if q:
        q_lower = f"%{q}%"
        query = query.filter(
            (Case.case_number.ilike(q_lower))
            | (Case.client_name.ilike(q_lower))
            | (Case.court_name.ilike(q_lower))
            | (Case.case_type.ilike(q_lower))
        )
    cases = query.all()
    return templates.TemplateResponse(
        name="cases.html",
        context={"request": request, "cases": cases, "query": q or ""},
    )


@app.get("/ui/cases/{case_id}", response_class=HTMLResponse)
def case_detail_page(
    request: Request,
    case_id: int,
    notice: str | None = None,
    prediction_probability: float | None = None,
    prediction_summary: str | None = None,
    prediction_risk: str | None = None,
    document_summary_id: int | None = None,
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    documents = db.query(Document).filter(Document.case_id == case_id).order_by(Document.created_at.desc()).all()
    hearings = db.query(Hearing).filter(Hearing.case_id == case_id).order_by(Hearing.hearing_date.asc()).all()
    deadlines = db.query(Deadline).filter(Deadline.case_id == case_id).order_by(Deadline.deadline.asc()).all()
    research_notes = (
        db.query(ResearchNote).filter(ResearchNote.case_id == case_id).order_by(ResearchNote.created_at.desc()).all()
    )
    summary_document = None
    if document_summary_id is not None:
        summary_document = db.query(Document).filter(Document.id == document_summary_id, Document.case_id == case_id).first()

    prediction = None
    if (
        prediction_probability is not None
        and prediction_summary
        and prediction_risk
    ):
        prediction = {
            "success_probability": round(prediction_probability * 100, 0),
            "summary": prediction_summary,
            "risk_analysis": prediction_risk,
        }

    document_summary = None
    if summary_document is not None:
        document_summary = {
            "document_type": summary_document.document_type,
            "summary": summarize_text(summary_document.content),
        }

    return templates.TemplateResponse(
        name="case_detail.html",
        context={
            "request": request,
            "case": case,
            "documents": documents,
            "hearings": hearings,
            "deadlines": deadlines,
            "latest_research_note": research_notes[0] if research_notes else None,
            "prediction": prediction,
            "document_summary": document_summary,
            "notice": notice,
        },
    )


@app.get("/ui/documents/upload", response_class=HTMLResponse)
def document_upload_page(request: Request, db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    return templates.TemplateResponse(
        name="document_upload.html",
        context={"request": request, "cases": cases},
    )


@app.get("/ui/drafts", response_class=HTMLResponse)
def draft_generator_page(
    request: Request,
    notice: str | None = None,
    selected_case_id: int | None = None,
    document_type: str = "written_statement",
    client_name: str = "",
    opponent_name: str = "",
    facts: str = "",
    demand: str = "",
    authority: str = "",
    additional_notes: str = "",
    generated_draft: str = "",
    db: Session = Depends(get_db),
):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    selected_case = None
    if selected_case_id is not None:
        selected_case = db.query(Case).filter(Case.id == selected_case_id).first()
    return templates.TemplateResponse(
        name="draft_generator.html",
        context={
            "request": request,
            "cases": cases,
            "selected_case": selected_case,
            "selected_case_id": selected_case_id,
            "document_type": document_type,
            "client_name": client_name,
            "opponent_name": opponent_name,
            "facts": facts,
            "demand": demand,
            "authority": authority,
            "additional_notes": additional_notes,
            "generated_draft": generated_draft,
            "notice": notice,
        },
    )


@app.post("/ui/drafts/generate", response_class=HTMLResponse)
def generate_draft_page(
    request: Request,
    case_id: int = Form(...),
    document_type: str = Form(...),
    client_name: str = Form(...),
    opponent_name: str = Form(...),
    facts: str = Form(...),
    demand: str = Form(...),
    authority: str = Form(...),
    additional_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    generated_draft = generate_legal_draft(
        document_type,
        case,
        client_name=client_name,
        opponent_name=opponent_name,
        facts=facts,
        demand=demand,
        authority=authority,
        additional_notes=additional_notes,
    )
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    return templates.TemplateResponse(
        name="draft_generator.html",
        context={
            "request": request,
            "cases": cases,
            "selected_case": case,
            "selected_case_id": case.id,
            "document_type": document_type,
            "client_name": client_name,
            "opponent_name": opponent_name,
            "facts": facts,
            "demand": demand,
            "authority": authority,
            "additional_notes": additional_notes,
            "generated_draft": generated_draft,
            "notice": "Draft generated. You can edit it before saving.",
        },
    )


@app.post("/ui/drafts/save")
def save_generated_draft(
    case_id: int = Form(...),
    document_type: str = Form(...),
    generated_draft: str = Form(...),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    document = Document(
        case_id=case.id,
        document_type=document_type,
        file_path=None,
        content=generated_draft,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    vector_store.add_text(
        generated_draft,
        {"case_id": case.id, "document_id": document.id, "document_type": document_type},
    )
    log_activity(
        db,
        action="Draft saved",
        details=f"Saved {document_type} draft for case {case.case_number}.",
        case_id=case.id,
    )
    return _redirect_to_case_detail(case.id, notice="Draft saved to Documents section.")


@app.post("/ui/cases/{case_id}/research")
def generate_research_note_ui(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    notes = generate_research_notes(case)
    research_note = ResearchNote(case_id=case.id, notes=notes)
    db.add(research_note)
    db.commit()
    log_activity(
        db,
        action="Research notes generated",
        details=f"Generated research notes for case {case.case_number}.",
        case_id=case.id,
    )
    return _redirect_to_case_detail(case.id, notice="Research notes generated successfully.")


@app.post("/ui/cases/{case_id}/predict")
def predict_case_ui(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    result = predict_outcome(case)
    log_activity(
        db,
        action="Outcome predicted",
        details=f"Generated outcome prediction for case {case.case_number}.",
        case_id=case.id,
    )
    return _redirect_to_case_detail(
        case.id,
        notice="Outcome prediction generated successfully.",
        prediction_probability=result["success_probability"],
        prediction_summary=result["summary"],
        prediction_risk=result["risk_analysis"],
    )


@app.post("/ui/cases/{case_id}/documents/generate")
def generate_document_ui(case_id: int, document_type: str = Form(...), db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    draft = generate_legal_draft(document_type, case)
    document = Document(case_id=case.id, document_type=document_type, file_path=None, content=draft)
    db.add(document)
    db.commit()
    db.refresh(document)
    vector_store.add_text(
        draft,
        {"case_id": case.id, "document_id": document.id, "document_type": document_type},
    )
    log_activity(
        db,
        action="AI draft generated",
        details=f"Generated {document_type} for case {case.case_number}.",
        case_id=case.id,
    )
    return _redirect_to_case_detail(
        case.id,
        notice=f"Drafted {document_type.replace('_', ' ')} successfully.",
        document_summary_id=document.id,
    )


@app.post("/ui/documents/{document_id}/summary")
def summarize_document_ui(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        return HTMLResponse(content="<h2>Document not found</h2>", status_code=404)

    log_activity(
        db,
        action="Document summarized",
        details=f"Generated summary for {document.document_type}.",
        case_id=document.case_id,
    )
    return _redirect_to_case_detail(
        document.case_id,
        notice="Document summary generated successfully.",
        document_summary_id=document.id,
    )
