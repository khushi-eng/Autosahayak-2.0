from fastapi.testclient import TestClient
from main import app
import json

client = TestClient(app, raise_server_exceptions=False)
response = client.get("/openapi.json")
if response.status_code == 200:
    data = response.json()
    paths = data.get("paths", {})
    for path, methods in paths.items():
        for method in methods:
            print(f"Testing {method.upper()} {path}")
            # Try a request with empty parameters
            if method.upper() == "GET":
                # For GET we can just pass some dummy path params if any
                p = path.replace("{case_id}", "1").replace("{document_id}", "1").replace("{deadline_id}", "1")
                res = client.get(p)
                if res.status_code == 500:
                    print(f"FAILED GET {p} - 500")
            elif method.upper() == "POST":
                p = path.replace("{case_id}", "1").replace("{document_id}", "1").replace("{deadline_id}", "1")
                res = client.post(p, json={}, data={})
                if res.status_code == 500:
                    print(f"FAILED POST {p} - 500")
                    print(res.text)
