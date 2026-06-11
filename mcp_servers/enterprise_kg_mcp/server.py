from __future__ import annotations

from typing import Any

from mcp_servers.common import ToolRegistry

try:
    from project.backend.knowledge_graph.kg_query_tool import (
        enterprise_kg_query,
        find_related_tickets as _find_related_tickets,
        get_customer_graph,
        trace_issue_impact,
    )
except ModuleNotFoundError:
    from backend.knowledge_graph.kg_query_tool import (
        enterprise_kg_query,
        find_related_tickets as _find_related_tickets,
        get_customer_graph,
        trace_issue_impact,
    )


registry = ToolRegistry("enterprise_kg_mcp")


@registry.tool(description="Query the enterprise graph around an entity.")
def query_enterprise_graph(entity: str, relation_type: str | None = None, depth: int = 2) -> dict[str, Any]:
    return enterprise_kg_query(entity, relation_type=relation_type, depth=depth)


@registry.tool(description="Get customer-centered graph context.")
def get_customer_context(customer_id: str) -> dict[str, Any]:
    return get_customer_graph(customer_id)


@registry.tool(description="Find graph-related support tickets for an entity.")
def find_related_tickets(entity_name: str) -> dict[str, Any]:
    return _find_related_tickets(entity_name)


@registry.tool(description="Trace issue impact scope across customers and products.")
def trace_impact_scope(issue_id: str) -> dict[str, Any]:
    return trace_issue_impact(issue_id)


if __name__ == "__main__":
    registry.cli()
