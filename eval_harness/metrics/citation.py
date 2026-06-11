"""Citation coverage metrics."""
from __future__ import annotations


def citation_coverage(answer: str, retrieved_doc_ids: list[str]) -> float:
    """Score whether an answer cites at least one retrieved doc ID.

    The first implementation uses explicit doc_id string matching. Later we can
    support structured citations emitted by the response generator.
    """
    if not answer or not retrieved_doc_ids:
        return 0.0
    answer_text = answer.lower()
    for doc_id in retrieved_doc_ids:
        if str(doc_id).lower() in answer_text:
            return 1.0
    return 0.0


def has_any_citation(answer: str) -> bool:
    text = (answer or "").lower()
    return "doc_id=" in text or "source" in text or "citation" in text

