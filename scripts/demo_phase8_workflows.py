from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.workflows.customer_reply_workflow import run_customer_reply_workflow
from backend.workflows.kg_enhanced_qa_workflow import run_kg_enhanced_qa_workflow
from backend.workflows.ticket_priority_workflow import run_ticket_priority_workflow


def fake_vector_retriever(query: str, top_k: int = 5) -> dict:
    return {
        "docs": [
            {
                "title": "SSO Access Troubleshooting",
                "doc_id": "demo-sso-doc",
                "source_type": "knowledge_base",
                "text": "For SSO access issues, verify identity mapping, account state, entitlement sync, and recent policy changes.",
            },
            {
                "title": "Runbook: Deploy / Upgrade / Roll Back perf-canary (Prod)",
                "doc_id": "demo-perf-doc",
                "source_type": "confluence",
                "text": "perf-canary rollout should validate metrics, overhead, alert routing, and rollback readiness before expansion.",
            },
        ][:top_k],
        "meta": {"retrieval_mode": "fake_demo"},
    }


def _compact(result: dict) -> dict:
    return {
        "workflow": result.get("workflow"),
        "plan": result.get("plan"),
        "answer": result.get("answer") or result.get("draft_reply"),
        "priority": result.get("priority"),
        "intent": result.get("intent"),
        "citations": result.get("citations") or result.get("response_sections", {}).get("citations"),
        "graph_paths": (result.get("graph_paths") or result.get("response_sections", {}).get("graph_paths") or [])[:5],
        "next_steps": result.get("next_steps"),
    }


def main() -> None:
    customer_query = "客户 CustQRWQE 之前有 SSO 工单，现在问部署 perf-canary 是否会影响访问，请结合历史和文档生成回复"
    qa_query = "perf-canary 谁负责，部署到 prod 时文档怎么说？"
    ticket_text = "CustQRWQE cannot login to SSO in production and says this is urgent."

    outputs = [
        _compact(run_customer_reply_workflow(customer_query, vector_retriever=fake_vector_retriever)),
        _compact(run_kg_enhanced_qa_workflow(qa_query, vector_retriever=fake_vector_retriever)),
        _compact(run_ticket_priority_workflow(ticket_text, product="SSO")),
    ]
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
