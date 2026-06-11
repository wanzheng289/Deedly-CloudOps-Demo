from backend.agents.tool_router import route_query
from backend.workflows.kg_rag_workflow import run_kg_rag_workflow


def test_route_query_detects_combo_customer_kg_vector_task():
    decision = route_query("客户 CustQRWQE 之前的 SSO 工单，结合文档和图谱生成回复")

    assert decision.customer_id == "CustQRWQE"
    assert decision.use_customer_profile is True
    assert decision.use_customer_tickets is True
    assert decision.use_enterprise_kg is True
    assert decision.use_vector_rag is True
    assert decision.draft_customer_reply is True
    assert decision.tool_sequence == [
        "get_customer_profile",
        "search_customer_tickets",
        "enterprise_kg_query",
        "search_enterprise_kb",
        "draft_customer_reply",
    ]


def test_kg_rag_workflow_returns_sections_with_injected_vector_retriever():
    def fake_retriever(query: str, top_k: int = 5):
        return {
            "docs": [
                {
                    "title": "SSO Access Troubleshooting",
                    "doc_id": "doc-sso",
                    "source_type": "kb",
                    "text": "Verify identity mapping and entitlement sync for SSO access issues.",
                }
            ],
            "meta": {"retrieval_mode": "test"},
        }

    result = run_kg_rag_workflow(
        "客户 CustQRWQE 之前 SSO 工单，结合文档和图谱生成回复",
        vector_retriever=fake_retriever,
    )

    assert result["route"]["use_enterprise_kg"] is True
    assert result["citations"][0]["doc_id"] == "doc-sso"
    assert result["graph_paths"]
    assert "建议回复" in result["answer"]
    assert result["open_questions"]
