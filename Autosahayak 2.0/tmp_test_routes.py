import urllib.request
import urllib.error

paths = [
    "/ui/cases",
    "/ui/cases/1",
    "/ui/cases/1/documents",
    "/ui/cases/1/hearings",
    "/ui/cases/1/research",
    "/ui/cases/1/scheduling",
    "/ui/cases/1/drafting",
]

for path in paths:
    url = f"http://127.0.0.1:8002{path}"
    try:
        resp = urllib.request.urlopen(url)
        print(path, resp.status)
    except urllib.error.HTTPError as e:
        print(path, 'HTTPError', e.code)
        print(e.read().decode('utf-8', 'ignore')[:800])
    except Exception as e:
        print(path, 'Error', type(e).__name__, e)
