from fastapi.testclient import TestClient
from main import app
import traceback

client = TestClient(app, raise_server_exceptions=True)
try:
    client.get("/ui/cases/1/documents/generate")
except Exception as e:
    traceback.print_exc()
