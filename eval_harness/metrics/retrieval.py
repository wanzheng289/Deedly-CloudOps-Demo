"""Retrieval metrics for RAG evaluation."""
from __future__ import annotations

from typing import Iterable


def _doc_id_set(items: Iterable[str]) -> set[str]:
    return {str(item).strip() for item in items if str(item).strip()}


def extract_retrieved_doc_ids(retrieved_docs: list[dict]) -> list[str]:
    """Extract unique retrieved doc IDs while preserving first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for doc in retrieved_docs:
        doc_id = str(doc.get("doc_id") or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(doc_id)
    return out


def recall_at_k(expected_doc_ids: list[str], retrieved_doc_ids: list[str], k: int) -> float:
    """Return 1.0 if any expected doc appears in top-k, else 0.0.

    EnterpriseRAG-Bench questions often have one gold document. This binary
    recall is easy to interpret for first-pass RAG iteration.
    """
    expected = _doc_id_set(expected_doc_ids)
    if not expected:
        return 0.0
    retrieved_top_k = _doc_id_set(retrieved_doc_ids[:k])
    return 1.0 if expected & retrieved_top_k else 0.0


def hit_doc_ids(expected_doc_ids: list[str], retrieved_doc_ids: list[str], k: int) -> list[str]:
    expected = _doc_id_set(expected_doc_ids)
    retrieved_top_k = retrieved_doc_ids[:k]
    return [doc_id for doc_id in retrieved_top_k if doc_id in expected]

