# Autosahayak 2.0

Backend-first FastAPI application for AI-powered legal workflow and court case management.

## Features

- Dashboard API with total cases, upcoming hearings, deadlines, and recent activity
- Case management with create, list, detail, and search support
- Document repository with upload, AI document generation, and summarization
- Hearings and deadline tracking
- Mock reminder workflow with background polling
- AI-powered research notes and case outcome prediction
- Minimal Jinja2 UI for dashboard, cases, case details, and document upload
- Server-rendered AI actions on case pages for prediction, research, draft generation, and summarization
- SQLite storage with SQLAlchemy ORM
- FAISS placeholder vector store
- OpenAI integration with automatic mock fallback when `OPENAI_API_KEY` is missing
- Automatic demo data seeding when the database is empty

## Project Structure

```text
Autosahayak 2.0/
├── main.py
├── requirements.txt
├── README.md
├── agents/
├── database/
├── routes/
├── schemas/
├── services/
├── static/
├── templates/
└── utils/
```

## Run

```powershell
cd "C:\Users\khush\OneDrive\Documents\Hackathon-vit\Autosahayak 2.0"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open:

- App UI: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`
- Draft Generator UI: `http://127.0.0.1:8000/ui/drafts`

## Demo Data

On first startup, the app seeds a small demo dataset into `data/autosahayak.db` if the database is empty. This gives you:

- 2 sample cases
- uploaded sample documents
- upcoming hearings
- deadlines, including one inside the reminder window
- one pre-seeded research note

To reset the demo data, delete `data/autosahayak.db` and restart the server.

## UI Agent Flow

Open any case from the dashboard or cases list and use the built-in actions to test the agents:

- `Predict Outcome`
- `Generate Research Notes`
- `Generate Draft Document`
- `Summarize` on any listed document

You can also use the dedicated Draft Generator page to:

- choose a legal document type
- enter client, facts, opponent, and demand
- edit the generated draft
- save it directly into the Documents section

## Important Routes

- `GET /dashboard`
- `POST /cases`
- `GET /cases`
- `GET /cases/{case_id}`
- `POST /documents/upload`
- `GET /documents/{case_id}`
- `POST /documents/generate`
- `GET /documents/summary/{document_id}`
- `POST /hearings`
- `GET /hearings/{case_id}`
- `POST /deadlines`
- `GET /deadlines/{case_id}`
- `POST /deadlines/send-reminder/{deadline_id}`
- `POST /ai/research/{case_id}`
- `POST /ai/predict/{case_id}`
- `POST /ai/summarize`

## Validation

The source files were syntax-validated with AST parsing in the local workspace. A normal bytecode compile pass was blocked by Windows permission locks on generated `__pycache__` files.
