from __future__ import annotations

from typing import Any

try:
    from project.backend.workflows.kg_rag_workflow import VectorRetriever, run_kg_rag_workflow
except ModuleNotFoundError:
    from backend.workflows.kg_rag_workflow import VectorRetriever, run_kg_rag_workflow


def run_customer_reply_workflow(
    query: str,
    customer_id: str | None = None,
    *,
    vector_retriever: VectorRetriever | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Generate a support reply using customer memory, KG paths, and document evidence."""
    evidence = run_kg_rag_workflow(
        query=query,
        customer_id=customer_id,
        vector_retriever=vector_retriever,
        top_k=top_k,
    )
    plan = [
        {"step": "identify_customer_and_product", "status": "completed"},
        {"step": "get_customer_profile", "status": "completed" if evidence.get("customer_profile") else "skipped"},
        {"step": "search_customer_tickets", "status": "completed" if evidence.get("customer_tickets") else "skipped"},
        {"step": "enterprise_kg_query", "status": "completed" if evidence.get("kg_graphs") else "skipped"},
        {"step": "search_enterprise_kb", "status": "completed" if evidence.get("citations") else "skipped"},
        {"step": "draft_reply", "status": "completed"},
    ]
    return {
        "workflow": "customer_reply_workflow",
        "query": query,
        "plan": plan,
        "draft_reply": evidence["answer"],
        "response_sections": {
            "answer": evidence["answer"],
            "citations": evidence["citations"],
            "graph_paths": evidence["graph_paths"],
            "open_questions": evidence["open_questions"],
        },
        "evidence": evidence,
    }
