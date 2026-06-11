from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_servers.customer_ops_mcp.server import registry as customer_ops_registry
from mcp_servers.enterprise_kb_mcp.server import registry as kb_registry
from mcp_servers.enterprise_kg_mcp.server import registry as kg_registry
from mcp_servers.eval_mcp.server import registry as eval_registry
from mcp_servers.memory_mcp.server import registry as memory_registry


def main() -> None:
    output = {
        "enterprise_kb_tools": [tool["name"] for tool in kb_registry.list_tools()],
        "enterprise_kg_tools": [tool["name"] for tool in kg_registry.list_tools()],
        "memory_tools": [tool["name"] for tool in memory_registry.list_tools()],
        "customer_ops_tools": [tool["name"] for tool in customer_ops_registry.list_tools()],
        "eval_tools": [tool["name"] for tool in eval_registry.list_tools()],
        "sample_calls": {
            "kb_search": kb_registry.call_tool("search_documents", {"query": "perf-canary deploy", "top_k": 2}),
            "kg_customer": kg_registry.call_tool("query_enterprise_graph", {"entity": "CustQRWQE", "depth": 1}),
            "memory_read": memory_registry.call_tool("read_memory", {"customer_id": "CustQRWQE", "limit": 3}),
            "customer_profile": customer_ops_registry.call_tool("get_customer_profile", {"customer_id": "CustQRWQE"}),
            "eval_dry_run": eval_registry.call_tool("run_eval_dataset", {"dataset": "enterprise_qa", "limit": 3, "run_retrieval": False}),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2)[:6000])


if __name__ == "__main__":
    main()
