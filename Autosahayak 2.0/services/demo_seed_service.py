from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database.models import ActivityLog, Case, Deadline, Document, Hearing, ResearchNote
from services.vector_store import vector_store


def seed_demo_data_if_empty(db: Session) -> bool:
    existing_case = db.query(Case.id).first()
    if existing_case:
        return False

    now = datetime.utcnow()
    cases = [
        Case(
            case_number="DEL-CIV-2026-0142",
            court_name="Delhi District Court",
            case_type="Civil Suit",
            parties_involved="Aarav Sharma vs. Horizon Builders Pvt. Ltd.",
            client_name="Aarav Sharma",
            client_email="aarav.sharma@example.com",
        ),
        Case(
            case_number="BLR-LAB-2026-0087",
            court_name="Bengaluru Labour Court",
            case_type="Employment Dispute",
            parties_involved="Nisha Rao vs. Vertex Analytics LLP",
            client_name="Nisha Rao",
            client_email="nisha.rao@example.com",
        ),
    ]
    db.add_all(cases)
    db.flush()

    documents = [
        Document(
            case_id=cases[0].id,
            document_type="plaint",
            file_path=None,
            content=(
                "The plaintiff submits that the builder failed to deliver possession within the agreed timeline "
                "despite receiving 92 percent of the total consideration."
            ),
        ),
        Document(
            case_id=cases[0].id,
            document_type="agreement_copy",
            file_path=None,
            content=(
                "Flat buyer agreement dated 14 January 2025. Clause 11 records the delivery commitment and "
                "compensation for delayed possession."
            ),
        ),
        Document(
            case_id=cases[1].id,
            document_type="termination_letter",
            file_path=None,
            content=(
                "Termination letter issued on alleged performance grounds without prior warning, domestic inquiry, "
                "or severance discussion."
            ),
        ),
    ]
    db.add_all(documents)
    db.flush()

    for document in documents:
        vector_store.add_text(
            document.content,
            {
                "case_id": document.case_id,
                "document_id": document.id,
                "document_type": document.document_type,
            },
        )

    hearings = [
        Hearing(
            case_id=cases[0].id,
            hearing_date=now + timedelta(days=5),
            notes="Court directed both parties to file short written submissions before the next listing.",
            next_action="Prepare chronology and annexure index.",
        ),
        Hearing(
            case_id=cases[1].id,
            hearing_date=now + timedelta(days=9),
            notes="Conciliation window remains open; respondent asked to produce employment records.",
            next_action="Collect salary slips and email trail from the client.",
        ),
    ]
    deadlines = [
        Deadline(
            case_id=cases[0].id,
            title="File additional affidavit",
            deadline=now + timedelta(hours=20),
            reminder_sent=False,
        ),
        Deadline(
            case_id=cases[1].id,
            title="Submit rejoinder draft",
            deadline=now + timedelta(days=3),
            reminder_sent=False,
        ),
    ]
    research_notes = [
        ResearchNote(
            case_id=cases[0].id,
            notes=(
                "Demo research note: focus on delay-compensation clauses, deficiency in service arguments, "
                "and decisions where possession timelines were treated as material terms."
            ),
        )
    ]
    activity = [
        ActivityLog(
            case_id=cases[0].id,
            action="Demo data loaded",
            details="Seeded civil suit sample with documents, hearing, deadline, and research note.",
        ),
        ActivityLog(
            case_id=cases[1].id,
            action="Demo data loaded",
            details="Seeded labour dispute sample with hearing, deadline, and termination document.",
        ),
    ]

    db.add_all(hearings + deadlines + research_notes + activity)
    db.commit()
    return True
