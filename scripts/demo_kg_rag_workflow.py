from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.workflows.kg_rag_workflow import run_kg_rag_workflow


def fake_vector_retriever(query: str, top_k: int = 5) -> dict:
    return {
        "docs": [
            {
                "title": "Runbook: Deploy / Upgrade / Roll Back perf-canary (Prod)",
                "doc_id": "demo-doc-perf-canary",
                "source_type": "confluence",
                "text": "perf-canary rollout should validate metrics, overhead, alert routing, and rollback readiness before expanding coverage.",
            },
            {
                "title": "SSO Access Troubleshooting",
                "doc_id": "demo-doc-sso",
                "source_type": "knowledge_base",
                "text": "For SSO access issues, verify account state, identity provider mapping, recent policy changes, and course entitlement sync.",
            },
        ][:top_k],
        "meta": {"retrieval_mode": "fake_demo"},
    }


def main() -> None:
    query = "客户 CustQRWQE 之前有 SSO 工单，现在问部署 perf-canary 是否会影响访问，请结合历史、图谱和文档生成回复"
    result = run_kg_rag_workflow(query, vector_retriever=fake_vector_retriever)
    compact = {
        "route": result["route"],
        "answer": result["answer"],
        "citations": result["citations"],
        "graph_paths": result["graph_paths"][:6],
        "open_questions": result["open_questions"],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
