from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_servers.common import ToolRegistry, WORKSPACE_ROOT, read_jsonl


registry = ToolRegistry("enterprise_kb_mcp")
DOCS_PATH = WORKSPACE_ROOT / "data" / "processed" / "enterprise_rag_bench" / "sample_documents.jsonl"


def _score_doc(doc: dict[str, Any], terms: list[str]) -> int:
    text = f"{doc.get('title', '')}\n{doc.get('content', '')}".lower()
    return sum(1 for term in terms if term in text)


@registry.tool(description="Search enterprise knowledge-base documents with a lightweight keyword fallback.")
def search_documents(query: str, top_k: int = 5) -> dict[str, Any]:
    terms = [term.lower() for term in query.split() if term.strip()]
    docs = read_jsonl(DOCS_PATH)
    ranked = []
    for doc in docs:
        score = _score_doc(doc, terms) if terms else 1
        if score > 0:
            ranked.append((score, doc))
    ranked.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, doc in ranked[:top_k]:
        results.append(
            {
                "doc_id": doc.get("doc_id"),
                "title": doc.get("title"),
                "source_type": doc.get("source_type"),
                "score": score,
                "text_preview": (doc.get("content") or "")[:500],
            }
        )
    return {"query": query, "count": len(results), "documents": results}


@registry.tool(description="Get one enterprise document by doc_id.")
def get_document(doc_id: str) -> dict[str, Any]:
    for doc in read_jsonl(DOCS_PATH):
        if doc.get("doc_id") == doc_id:
            return {"found": True, "document": doc}
    return {"found": False, "doc_id": doc_id}


@registry.tool(description="List source types available in the enterprise knowledge base sample.")
def list_sources() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for doc in read_jsonl(DOCS_PATH):
        source_type = doc.get("source_type") or "unknown"
        counts[source_type] = counts.get(source_type, 0) + 1
    return {"sources": counts, "source_count": len(counts)}


if __name__ == "__main__":
    registry.cli()
