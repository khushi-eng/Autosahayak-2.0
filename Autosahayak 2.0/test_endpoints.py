import traceback
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

paths = [
    "/ui/cases",
    "/ui/cases/1",
    "/ui/cases/1/documents",
    "/ui/cases/1/hearings",
    "/ui/cases/1/research",
    "/ui/cases/1/scheduling",
    "/ui/cases/1/drafting",
    "/dashboard",
    "/ui/overview",
    "/ui/drafts",
    "/ui/documents/upload"
]

for path in paths:
    response = client.get(path)
    if response.status_code >= 500:
        print(f"FAILED {path} - {response.status_code}")
        print(response.text)
    else:
        print(f"OK {path} - {response.status_code}")
