from __future__ import annotations

import json
from typing import Any

try:
    from langchain_core.tools import tool
except Exception:  # pragma: no cover
    def tool(name: str):  # type: ignore
        def decorator(func):
            func.name = name
            return func

        return decorator

try:
    from project.backend.knowledge_graph.kg_query_tool import (
        enterprise_kg_query as _enterprise_kg_query,
        find_owner_team as _find_owner_team,
        find_related_tickets as _find_related_tickets,
        get_customer_graph as _get_customer_graph,
        get_product_dependency_graph as _get_product_dependency_graph,
        trace_issue_impact as _trace_issue_impact,
    )
except ModuleNotFoundError:
    from backend.knowledge_graph.kg_query_tool import (
        enterprise_kg_query as _enterprise_kg_query,
        find_owner_team as _find_owner_team,
        find_related_tickets as _find_related_tickets,
        get_customer_graph as _get_customer_graph,
        get_product_dependency_graph as _get_product_dependency_graph,
        trace_issue_impact as _trace_issue_impact,
    )


def _json_result(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _compact_graph(graph: dict, max_nodes: int = 40, max_relations: int = 60) -> dict:
    compact = dict(graph)
    compact["nodes"] = compact.get("nodes", [])[:max_nodes]
    compact["relations"] = compact.get("relations", [])[:max_relations]
    compact["node_count"] = len(graph.get("nodes", []))
    compact["relation_count"] = len(graph.get("relations", []))
    return compact


@tool("enterprise_kg_query")
def enterprise_kg_query(entity: str, relation_type: str | None = None, depth: int = 2) -> str:
    """Query the enterprise knowledge graph around an entity."""
    return _json_result(_compact_graph(_enterprise_kg_query(entity, relation_type=relation_type, depth=depth)))


@tool("get_customer_graph")
def get_customer_graph(customer_id: str) -> str:
    """Get customer-centered graph context."""
    return _json_result(_compact_graph(_get_customer_graph(customer_id)))


@tool("get_product_dependency_graph")
def get_product_dependency_graph(product_name: str) -> str:
    """Get product dependency graph context."""
    return _json_result(_compact_graph(_get_product_dependency_graph(product_name)))


@tool("find_related_tickets")
def find_related_tickets(entity_name: str) -> str:
    """Find support tickets related to a product, customer, issue, or service."""
    return _json_result(_compact_graph(_find_related_tickets(entity_name)))


@tool("find_owner_team")
def find_owner_team(service_or_module: str) -> str:
    """Find likely owner teams for a service or module."""
    return _json_result(_compact_graph(_find_owner_team(service_or_module)))


@tool("trace_issue_impact")
def trace_issue_impact(issue_id: str) -> str:
    """Trace impacted customers/products for an issue."""
    return _json_result(_compact_graph(_trace_issue_impact(issue_id)))
