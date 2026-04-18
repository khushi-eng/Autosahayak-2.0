from __future__ import annotations

from typing import Any

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


class SimpleVectorStore:
    def __init__(self) -> None:
        self.index: Any | None = faiss.IndexFlatL2(8) if faiss else None
        self.entries: list[dict[str, Any]] = []

    def add_text(self, text: str, metadata: dict[str, Any]) -> None:
        self.entries.append({"text": text, "metadata": metadata})

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        lowered = query.lower()
        matches = [entry for entry in self.entries if lowered in entry["text"].lower()]
        return matches[:limit]


vector_store = SimpleVectorStore()

