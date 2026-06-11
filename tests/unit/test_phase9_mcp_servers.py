from mcp_servers.customer_ops_mcp.server import registry as customer_ops_registry
from mcp_servers.enterprise_kb_mcp.server import registry as kb_registry
from mcp_servers.enterprise_kg_mcp.server import registry as kg_registry
from mcp_servers.eval_mcp.server import registry as eval_registry
from mcp_servers.memory_mcp.server import registry as memory_registry


def test_enterprise_kb_mcp_tools_and_search():
    names = {tool["name"] for tool in kb_registry.list_tools()}
    assert {"search_documents", "get_document", "list_sources"}.issubset(names)
    result = kb_registry.call_tool("search_documents", {"query": "perf-canary", "top_k": 1})
    assert result["count"] >= 1


def test_enterprise_kg_mcp_customer_query():
    names = {tool["name"] for tool in kg_registry.list_tools()}
    assert {"query_enterprise_graph", "get_customer_context", "find_related_tickets", "trace_impact_scope"}.issubset(names)
    result = kg_registry.call_tool("query_enterprise_graph", {"entity": "CustQRWQE", "depth": 1})
    assert result["nodes"]
    assert result["relations"]


def test_memory_and_customer_ops_mcp_read_paths():
    memory_names = {tool["name"] for tool in memory_registry.list_tools()}
    customer_names = {tool["name"] for tool in customer_ops_registry.list_tools()}
    assert {"read_memory", "write_memory", "search_memory", "delete_memory"}.issubset(memory_names)
    assert {"get_customer_profile", "search_customer_tickets", "create_followup_task", "update_ticket_status"}.issubset(customer_names)

    profile = customer_ops_registry.call_tool("get_customer_profile", {"customer_id": "CustQRWQE"})
    tickets = customer_ops_registry.call_tool("search_customer_tickets", {"customer_id": "CustQRWQE", "query": "SSO", "limit": 1})
    assert profile["found"] is True
    assert tickets["ticket_count"] >= 1


def test_eval_mcp_dry_run_and_scoring():
    names = {tool["name"] for tool in eval_registry.list_tools()}
    assert {"run_eval_dataset", "score_answer", "compare_prompt_versions"}.issubset(names)
    report = eval_registry.call_tool("run_eval_dataset", {"dataset": "enterprise_qa", "limit": 2, "run_retrieval": False})
    score = eval_registry.call_tool("score_answer", {"answer": "Use doc-a", "retrieved_doc_ids": ["doc-a"]})
    assert report["ok"] is True
    assert report["summary"]["case_count"] == 2
    assert score["citation_coverage"] == 1.0
