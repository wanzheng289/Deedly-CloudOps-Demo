from backend.workflows.customer_reply_workflow import run_customer_reply_workflow
from backend.workflows.kg_enhanced_qa_workflow import run_kg_enhanced_qa_workflow
from backend.workflows.ticket_priority_workflow import run_ticket_priority_workflow


def fake_vector_retriever(query: str, top_k: int = 5):
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


def test_customer_reply_workflow_returns_draft_sections():
    result = run_customer_reply_workflow(
        "客户 CustQRWQE 之前有 SSO 工单，请结合文档生成回复",
        vector_retriever=fake_vector_retriever,
    )

    assert result["workflow"] == "customer_reply_workflow"
    assert "建议回复" in result["draft_reply"]
    assert result["response_sections"]["citations"]
    assert result["response_sections"]["graph_paths"]


def test_kg_enhanced_qa_workflow_returns_citations_and_graph_paths():
    result = run_kg_enhanced_qa_workflow(
        "SSO 文档怎么说，相关团队是谁？",
        vector_retriever=fake_vector_retriever,
    )

    assert result["workflow"] == "kg_enhanced_qa_workflow"
    assert result["citations"][0]["doc_id"] == "doc-sso"
    assert result["plan"][-1]["step"] == "compose_answer_with_citations_and_paths"


def test_ticket_priority_workflow_classifies_high_access_issue():
    result = run_ticket_priority_workflow(
        "CustQRWQE cannot login to SSO in production and says this is urgent.",
        product="SSO",
    )

    assert result["workflow"] == "ticket_priority_workflow"
    assert result["intent"] == "access_issue"
    assert result["sentiment"] == "negative"
    assert result["priority"] == "high"
    assert result["next_steps"]
