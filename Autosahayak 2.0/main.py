import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
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
from services.calendar_service import send_calendar_invite
from services.dashboard_service import get_dashboard_data
from services.demo_seed_service import seed_demo_data_if_empty
from services.document_service import delete_upload_file, save_upload_file
from services.reminder_service import reminder_worker
from services.vector_store import vector_store
from utils.datetime_utils import (
    APP_TIMEZONE_NAME,
    ensure_utc,
    format_app_datetime,
    parse_datetime_local_input,
)
from utils.logging_config import configure_logging, get_logger


configure_logging()
logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def format_local_datetime(value, fmt: str = "%d %b %Y %I:%M %p") -> str:
    if not isinstance(value, datetime):
        return value
    return format_app_datetime(value, fmt)

templates.env.filters["local_datetime"] = format_local_datetime

DOCUMENT_TYPE_CONFIG = {
    "legal_notice": {
        "label": "Legal Notice",
        "mandatory_fields": [
            ("client_name", "Client name"),
            ("opponent_name", "Opposite party"),
            ("facts", "Facts of the matter"),
            ("demand", "Demand or relief"),
            ("authority", "Authority or recipient"),
        ],
        "description": "Send a formal legal notice before filing or escalating the matter.",
    },
    "complaint": {
        "label": "Complaint",
        "mandatory_fields": [
            ("client_name", "Complainant name"),
            ("opponent_name", "Respondent / accused"),
            ("facts", "Complaint facts"),
            ("demand", "Relief requested"),
            ("authority", "Forum / court"),
        ],
        "description": "Prepare a complaint with the core allegations and reliefs.",
    },
    "written_statement": {
        "label": "Written Statement",
        "mandatory_fields": [
            ("client_name", "Client name"),
            ("opponent_name", "Plaintiff / opposite party"),
            ("facts", "Defence facts"),
            ("demand", "Prayer"),
            ("authority", "Court"),
        ],
        "description": "Prepare the defence position with facts, denials, and prayer.",
    },
    "affidavit": {
        "label": "Affidavit",
        "mandatory_fields": [
            ("client_name", "Deponent name"),
            ("facts", "Affidavit statements"),
            ("authority", "Court / authority"),
        ],
        "description": "Draft a sworn statement based on the matter record.",
    },
    "application": {
        "label": "Application",
        "mandatory_fields": [
            ("client_name", "Applicant name"),
            ("facts", "Grounds / facts"),
            ("demand", "Relief sought"),
            ("authority", "Court / authority"),
        ],
        "description": "Draft an interim or procedural application for the case.",
    },
}


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    return ensure_utc(value)


def _ensure_database_schema() -> None:
    with engine.begin() as conn:
        result = conn.execute(text("PRAGMA table_info(hearings)"))
        columns = {row[1] for row in result}
        if "next_hearing_date" not in columns:
            conn.execute(text("ALTER TABLE hearings ADD COLUMN next_hearing_date DATETIME"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_database_schema()
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


def _get_document_config(selected_type: str) -> dict:
    return DOCUMENT_TYPE_CONFIG.get(selected_type, DOCUMENT_TYPE_CONFIG["written_statement"])


def _build_draft_state(
    case: Case,
    *,
    document_type: str = "written_statement",
    client_name: str | None = None,
    opponent_name: str = "",
    facts: str = "",
    demand: str = "",
    authority: str | None = None,
    additional_notes: str = "",
    generated_draft: str = "",
) -> dict:
    return {
        "document_type": document_type,
        "client_name": client_name or case.client_name,
        "opponent_name": opponent_name,
        "facts": facts,
        "demand": demand,
        "authority": authority or case.court_name,
        "additional_notes": additional_notes,
        "generated_draft": generated_draft,
    }


def _build_case_cards(db: Session, q: str | None = None) -> list[dict]:
    query = db.query(Case).order_by(Case.created_at.desc())
    if q:
        q_lower = f"%{q}%"
        query = query.filter(
            (Case.case_number.ilike(q_lower))
            | (Case.client_name.ilike(q_lower))
            | (Case.court_name.ilike(q_lower))
            | (Case.case_type.ilike(q_lower))
        )

    now = datetime.now(timezone.utc)
    cards = []
    for case in query.all():
        next_hearing = (
            db.query(Hearing)
            .filter(Hearing.case_id == case.id, Hearing.hearing_date >= now)
            .order_by(Hearing.hearing_date.asc())
            .first()
        )
        upcoming_deadline = (
            db.query(Deadline)
            .filter(Deadline.case_id == case.id, Deadline.deadline >= now)
            .order_by(Deadline.deadline.asc())
            .first()
        )
        next_anchor = _as_utc_datetime(next_hearing.hearing_date) if next_hearing else None
        if next_anchor:
            days_to_hearing = max((next_anchor.date() - now.date()).days, 0)
            if days_to_hearing <= 2:
                priority = "High"
            elif days_to_hearing <= 7:
                priority = "Medium"
            else:
                priority = "Planned"
        else:
            days_to_hearing = None
            priority = "No Hearing"
        cards.append(
            {
                "case": case,
                "next_hearing": next_hearing,
                "upcoming_deadline": upcoming_deadline,
                "priority": priority,
                "days_to_hearing": days_to_hearing,
                "document_count": db.query(Document).filter(Document.case_id == case.id).count(),
            }
        )

    return sorted(
        cards,
        key=lambda item: (
            item["next_hearing"].hearing_date if item["next_hearing"] else datetime.max,
            item["case"].created_at,
        ),
    )


def _build_hearing_intelligence(hearings: list[Hearing]) -> tuple[list[dict], str | None]:
    if not hearings:
        return [], None

    sorted_hearings = sorted(hearings, key=lambda hearing: hearing.hearing_date)
    entries = []
    running_points = []
    for index, hearing in enumerate(sorted_hearings, start=1):
        hearing_doc = (
            f"Hearing {index}\n"
            f"Date: {format_app_datetime(hearing.hearing_date)} ({APP_TIMEZONE_NAME})\n"
            f"Proceedings: {hearing.notes}\n"
            f"Next Action: {hearing.next_action}"
        )
        running_points.append(
            f"Hearing {index} on {format_app_datetime(hearing.hearing_date, '%d %b %Y')}: {hearing.notes} Next action: {hearing.next_action}."
        )
        entries.append({"hearing": hearing, "document": hearing_doc})

    summary = " ".join(running_points)
    return entries, summarize_text(summary)


def _build_case_workspace_context(
    request: Request,
    db: Session,
    case: Case,
    *,
    notice: str | None = None,
    prediction: dict | None = None,
    summary_document: Document | None = None,
    draft_state: dict | None = None,
) -> dict:
    documents = db.query(Document).filter(Document.case_id == case.id).order_by(Document.created_at.desc()).all()
    hearings = db.query(Hearing).filter(Hearing.case_id == case.id).order_by(Hearing.hearing_date.asc()).all()
    deadlines = db.query(Deadline).filter(Deadline.case_id == case.id).order_by(Deadline.deadline.asc()).all()
    research_notes = (
        db.query(ResearchNote).filter(ResearchNote.case_id == case.id).order_by(ResearchNote.created_at.desc()).all()
    )

    document_summary = None
    if summary_document is not None:
        document_summary = {
            "id": summary_document.id,
            "document_type": summary_document.document_type,
            "summary": summarize_text(summary_document.content),
        }

    hearing_documents, hearing_summary = _build_hearing_intelligence(hearings)
    current_time = datetime.now(timezone.utc)
    next_hearing = next(
        (hearing for hearing in hearings if (_as_utc_datetime(hearing.hearing_date) or current_time) >= current_time),
        None,
    )
    upcoming_deadline = next(
        (deadline for deadline in deadlines if (_as_utc_datetime(deadline.deadline) or current_time) >= current_time),
        None,
    )
    active_draft_state = draft_state or _build_draft_state(case)

    return {
        "request": request,
        "case": case,
        "documents": documents,
        "hearings": hearings,
        "deadlines": deadlines,
        "research_notes": research_notes,
        "latest_research_note": research_notes[0] if research_notes else None,
        "prediction": prediction,
        "document_summary": document_summary,
        "notice": notice,
        "next_hearing": next_hearing,
        "upcoming_deadline": upcoming_deadline,
        "hearing_documents": hearing_documents,
        "hearing_summary": hearing_summary,
        "document_type_options": DOCUMENT_TYPE_CONFIG,
        "draft_state": active_draft_state,
        "active_document_config": _get_document_config(active_draft_state["document_type"]),
    }


@app.get("/dashboard")
def dashboard_api(db: Session = Depends(get_db)):
    return get_dashboard_data(db)


@app.get("/", response_class=HTMLResponse)
def root_page():
    return RedirectResponse(url="/ui/cases", status_code=302)


@app.get("/ui/overview", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    data = get_dashboard_data(db)
    cases = _build_case_cards(db)[:5]
    return templates.TemplateResponse(
        name="dashboard.html",
        context={"request": request, "dashboard": data, "case_cards": cases},
    )


@app.get("/ui/cases", response_class=HTMLResponse)
def cases_page(
    request: Request,
    q: str | None = None,
    notice: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    case_cards = _build_case_cards(db, q=q)
    return templates.TemplateResponse(
        name="cases.html",
        context={
            "request": request,
            "case_cards": case_cards,
            "query": q or "",
            "notice": notice,
            "error": error,
        },
    )


@app.get("/ui/cases/{case_id}/drafting", response_class=HTMLResponse)
def case_drafting_page(
    request: Request,
    case_id: int,
    notice: str | None = None,
    db: Session = Depends(get_db),
):
    # Redirect to documents page since drafting is now integrated there
    return RedirectResponse(url=f"/ui/cases/{case_id}/documents", status_code=302)


@app.get("/ui/cases/{case_id}/research", response_class=HTMLResponse)
def case_research_page(
    request: Request,
    case_id: int,
    notice: str | None = None,
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    research_notes = db.query(ResearchNote).filter(ResearchNote.case_id == case.id).order_by(ResearchNote.created_at.desc()).all()
    context = {
        "request": request,
        "case": case,
        "research_notes": research_notes,
        "notice": notice,
    }
    return templates.TemplateResponse(name="case_research.html", context=context)


@app.get("/ui/cases/{case_id}/scheduling", response_class=HTMLResponse)
def case_scheduling_page(
    request: Request,
    case_id: int,
    notice: str | None = None,
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    deadlines = db.query(Deadline).filter(Deadline.case_id == case.id).order_by(Deadline.deadline.asc()).all()
    context = {
        "request": request,
        "case": case,
        "deadlines": deadlines,
        "notice": notice,
    }
    return templates.TemplateResponse(name="case_scheduling.html", context=context)


@app.get("/ui/cases/{case_id}/hearings", response_class=HTMLResponse)
def case_hearings_page(
    request: Request,
    case_id: int,
    notice: str | None = None,
    prediction_probability: float | None = None,
    prediction_summary: str | None = None,
    prediction_risk: str | None = None,
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    hearings = db.query(Hearing).filter(Hearing.case_id == case.id).order_by(Hearing.hearing_date.asc()).all()
    hearing_documents, hearing_summary = _build_hearing_intelligence(hearings)
    prediction = None
    if prediction_probability is not None and prediction_summary and prediction_risk:
        prediction = {
            "success_probability": round(prediction_probability * 100, 0),
            "summary": prediction_summary,
            "risk_analysis": prediction_risk,
        }

    context = {
        "request": request,
        "case": case,
        "hearings": hearings,
        "hearing_documents": hearing_documents,
        "hearing_summary": hearing_summary,
        "prediction": prediction,
        "notice": notice,
    }
    return templates.TemplateResponse(name="case_hearings.html", context=context)


@app.get("/ui/cases/{case_id}/documents", response_class=HTMLResponse)
def case_documents_page(
    request: Request,
    case_id: int,
    notice: str | None = None,
    document_summary_id: int | None = None,
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    documents = db.query(Document).filter(Document.case_id == case.id).order_by(Document.created_at.desc()).all()
    document_summary = None
    if document_summary_id is not None:
        summary_doc = db.query(Document).filter(Document.id == document_summary_id, Document.case_id == case_id).first()
        if summary_doc:
            document_summary = {
                "id": summary_doc.id,
                "document_type": summary_doc.document_type,
                "summary": summarize_text(summary_doc.content),
            }

    context = {
        "request": request,
        "case": case,
        "documents": documents,
        "document_summary": document_summary,
        "notice": notice,
        "draft_state": _build_draft_state(case),
        "document_type_options": DOCUMENT_TYPE_CONFIG,
        "active_document_config": _get_document_config("written_statement"),
    }
    return templates.TemplateResponse(name="case_documents.html", context=context)


@app.post("/ui/cases/{case_id}/documents/upload")
async def upload_case_document_ui(
    case_id: int,
    document_type: str = Form(...),
    content: str = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    file_path = await save_upload_file(file, f"case_{case_id}")
    document = Document(case_id=case.id, document_type=document_type, file_path=file_path, content=content)
    db.add(document)
    db.commit()
    db.refresh(document)
    vector_store.add_text(content, {"case_id": case.id, "document_id": document.id, "document_type": document_type})
    log_activity(
        db,
        action="Document uploaded",
        details=f"Stored {document_type} for case {case.case_number}.",
        case_id=case.id,
    )
    return RedirectResponse(url=f"/ui/cases/{case.id}/documents?notice=Document uploaded to repository.", status_code=303)


@app.post("/ui/cases/{case_id}/documents/generate")
def generate_case_document_ui(
    request: Request,
    case_id: int,
    document_type: str = Form(...),
    client_name: str = Form(...),
    opponent_name: str = Form(...),
    facts: str = Form(...),
    demand: str = Form(...),
    authority: str = Form(...),
    additional_notes: str = Form(...),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    case_data = {
        "id": case.id,
        "case_number": case.case_number,
        "case_type": case.case_type,
        "client_name": case.client_name,
        "client_email": case.client_email,
        "court_name": case.court_name,
    }
    draft = generate_legal_draft(
        document_type,
        case,
        client_name=client_name,
        opponent_name=opponent_name,
        facts=facts,
        demand=demand,
        authority=authority,
        additional_notes=additional_notes,
    )
    document = Document(case_id=case_data["id"], document_type=document_type, file_path=None, content=draft)
    db.add(document)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        draft_state = _build_draft_state(
            case,
            document_type=document_type,
            client_name=client_name,
            opponent_name=opponent_name,
            facts=facts,
            demand=demand,
            authority=authority,
            additional_notes=additional_notes,
            generated_draft=draft,
        )
        return templates.TemplateResponse(
            name="case_documents.html",
            context={
                "request": request,
                "case": case_data,
                "documents": [],
                "document_summary": None,
                "notice": "Document generated, but it could not be saved because the database is temporarily unavailable.",
                "draft_state": draft_state,
                "document_type_options": DOCUMENT_TYPE_CONFIG,
                "active_document_config": _get_document_config(document_type),
            },
            status_code=200,
        )
    db.refresh(document)
    vector_store.add_text(draft, {"case_id": case_data["id"], "document_id": document.id, "document_type": document_type})
    log_activity(
        db,
        action="AI draft generated",
        details=f"Generated {document_type} for case {case_data['case_number']}.",
        case_id=case_data["id"],
    )
    return RedirectResponse(url=f"/ui/cases/{case_data['id']}/documents?notice=AI-generated document added to repository.", status_code=303)


@app.get("/ui/cases/{case_id}/documents/generate")
def generate_case_document_page(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    documents = db.query(Document).filter(Document.case_id == case.id).order_by(Document.created_at.desc()).all()
    return templates.TemplateResponse(
        name="case_documents.html",
        context={
            "request": request,
            "case": case,
            "documents": documents,
            "document_summary": None,
            "notice": "Use the AI-Generated Document form in this section to generate a document.",
            "draft_state": _build_draft_state(case),
            "document_type_options": DOCUMENT_TYPE_CONFIG,
            "active_document_config": _get_document_config("written_statement"),
        },
    )


@app.post("/ui/cases/{case_id}/delete")
def delete_case_ui(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    case_number = case.case_number
    db.delete(case)
    db.commit()
    log_activity(db, action="Case deleted", details=f"Deleted case {case_number}.", case_id=case_id)
    return RedirectResponse(url="/ui/cases?notice=Case deleted successfully.", status_code=303)


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

    summary_document = None
    if document_summary_id is not None:
        summary_document = db.query(Document).filter(Document.id == document_summary_id, Document.case_id == case_id).first()

    prediction = None
    if prediction_probability is not None and prediction_summary and prediction_risk:
        prediction = {
            "success_probability": round(prediction_probability * 100, 0),
            "summary": prediction_summary,
            "risk_analysis": prediction_risk,
        }

    context = _build_case_workspace_context(
        request,
        db,
        case,
        notice=notice,
        prediction=prediction,
        summary_document=summary_document,
    )
    return templates.TemplateResponse(name="case_detail.html", context=context)


@app.post("/ui/documents/{document_id}/delete")
def delete_document_ui(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        return HTMLResponse(content="<h2>Document not found</h2>", status_code=404)

    case_id = document.case_id
    doc_type = document.document_type
    if document.file_path:
        delete_upload_file(document.file_path)
    vector_store.remove_document(document.id)
    db.delete(document)
    db.commit()
    log_activity(db, action="Document deleted", details=f"Deleted {doc_type} from repository.", case_id=case_id)
    return RedirectResponse(url=f"/ui/cases/{case_id}/documents?notice=Document deleted from repository.", status_code=303)


@app.get("/ui/documents/{document_id}/download")
def download_document_ui(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document or not document.file_path:
        return HTMLResponse(content="<h2>Document file not found</h2>", status_code=404)

    return FileResponse(path=document.file_path, filename=Path(document.file_path).name, media_type="application/octet-stream")


@app.post("/ui/cases/{case_id}/hearings/add")
def add_hearing_ui(
    case_id: int,
    hearing_date: str = Form(...),
    next_hearing_date: str | None = Form(None),
    notes: str = Form(...),
    next_action: str = Form(...),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    hearing_date_dt = parse_datetime_local_input(hearing_date)
    next_hearing_date_dt = parse_datetime_local_input(next_hearing_date)
    hearing = Hearing(
        case_id=case.id,
        hearing_date=hearing_date_dt,
        next_hearing_date=next_hearing_date_dt,
        notes=notes,
        next_action=next_action,
    )
    db.add(hearing)
    db.commit()
    db.refresh(hearing)
    log_activity(
        db,
        action="Hearing intelligence updated",
        details=f"Added hearing record for {case.case_number} on {hearing.hearing_date.isoformat()}.",
        case_id=case.id,
    )

    email_sent = False
    if next_hearing_date_dt:
        recipient = os.getenv("LAWYER_EMAIL") or case.client_email
        subject = f"Next hearing scheduled for case {case.case_number}"
        body = (
            f"A next hearing has been scheduled for case {case.case_number}.\n\n"
            f"Case: {case.case_type}\n"
            f"Court: {case.court_name}\n"
            f"Next hearing date: {next_hearing_date_dt.isoformat()}\n"
            f"Notes: {notes}\n"
            f"Next action: {next_action}\n"
        )
        try:
            email_sent = send_calendar_invite(
                recipient_email=recipient,
                subject=subject,
                body=body,
                start_dt=next_hearing_date_dt,
                duration_minutes=60,
                location=case.court_name,
            )
        except Exception as exc:
            logger.warning("Calendar invite send failed: %s", exc)

    notice = "Hearing notes captured and intelligence updated."
    if email_sent:
        notice += " Calendar invite email sent."
    return RedirectResponse(url=f"/ui/cases/{case.id}/hearings?{urlencode({'notice': notice})}", status_code=303)


@app.post("/ui/cases/{case_id}/deadlines/add")
def add_deadline_ui(
    case_id: int,
    title: str = Form(...),
    deadline: str = Form(...),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    deadline_dt = parse_datetime_local_input(deadline)
    if deadline_dt is None:
        return HTMLResponse(content="<h2>Invalid deadline</h2>", status_code=400)

    item = Deadline(case_id=case.id, title=title, deadline=deadline_dt)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_activity(
        db,
        action="Scheduling item added",
        details=f"Added deadline '{title}' for case {case.case_number}.",
        case_id=case.id,
    )
    return RedirectResponse(url=f"/ui/cases/{case.id}/scheduling?notice=Scheduling system updated.", status_code=303)


@app.get("/ui/documents/upload", response_class=HTMLResponse)
def document_upload_page(
    request: Request,
    selected_case_id: int | None = None,
    db: Session = Depends(get_db),
):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    return templates.TemplateResponse(
        name="document_upload.html",
        context={"request": request, "cases": cases, "selected_case_id": selected_case_id},
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
            "document_type_options": DOCUMENT_TYPE_CONFIG,
            "active_document_config": _get_document_config(document_type),
        },
    )


@app.post("/ui/drafts/generate", response_class=HTMLResponse)
def generate_draft_page(
    request: Request,
    case_id: int = Form(...),
    document_type: str = Form(...),
    client_name: str = Form(...),
    opponent_name: str = Form(""),
    facts: str = Form(...),
    demand: str = Form(""),
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
            "document_type_options": DOCUMENT_TYPE_CONFIG,
            "active_document_config": _get_document_config(document_type),
        },
    )


@app.post("/ui/cases/{case_id}/drafts/generate", response_class=HTMLResponse)
def generate_case_draft_ui(
    request: Request,
    case_id: int,
    document_type: str = Form(...),
    client_name: str = Form(...),
    opponent_name: str = Form(""),
    facts: str = Form(...),
    demand: str = Form(""),
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
    # Since drafting is now in documents, create the document directly
    document = Document(case_id=case.id, document_type=document_type, file_path=None, content=generated_draft)
    db.add(document)
    db.commit()
    db.refresh(document)
    vector_store.add_text(generated_draft, {"case_id": case.id, "document_id": document.id, "document_type": document_type})
    log_activity(
        db,
        action="AI draft generated",
        details=f"Generated {document_type} for case {case.case_number}.",
        case_id=case.id,
    )
    return RedirectResponse(url=f"/ui/cases/{case.id}/documents?notice=AI-generated legal document added to repository.", status_code=303)


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
    return RedirectResponse(
        url=f"/ui/cases/{case.id}/documents?notice=Draft saved to Documents section.",
        status_code=303,
    )


@app.post("/ui/cases/{case_id}/research")
def generate_research_note_ui(request: Request, case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return HTMLResponse(content="<h2>Case not found</h2>", status_code=404)

    case_data = {
        "id": case.id,
        "case_number": case.case_number,
        "case_type": case.case_type,
        "client_name": case.client_name,
        "client_email": case.client_email,
        "court_name": case.court_name,
    }
    notes = generate_research_notes(case)
    research_note = ResearchNote(case_id=case_data["id"], notes=notes)
    db.add(research_note)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        transient_note = {
            "notes": notes,
            "created_at": datetime.now(timezone.utc),
        }
        return templates.TemplateResponse(
            name="case_research.html",
            context={
                "request": request,
                "case": case_data,
                "research_notes": [transient_note],
                "notice": "Research note generated, but it could not be saved because the database is temporarily unavailable.",
            },
            status_code=200,
        )
    log_activity(
        db,
        action="Research notes generated",
        details=f"Generated research notes for case {case_data['case_number']}.",
        case_id=case_data["id"],
    )
    return RedirectResponse(url=f"/ui/cases/{case_data['id']}/research?notice=Research notes generated successfully.", status_code=303)


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
    return RedirectResponse(
        url=f"/ui/cases/{case.id}/hearings?{urlencode({'notice': 'Outcome prediction generated successfully.', 'prediction_probability': result['success_probability'], 'prediction_summary': result['summary'], 'prediction_risk': result['risk_analysis']})}",
        status_code=303,
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
    return RedirectResponse(
        url=f"/ui/cases/{document.case_id}/documents?{urlencode({'notice': 'Document summary generated successfully.', 'document_summary_id': document.id})}",
        status_code=303,
    )
