"""Enterprise KG query tools with local JSONL fallback."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from project.backend.knowledge_graph.graph_builder import load_local_graph
except ModuleNotFoundError:
    from backend.knowledge_graph.graph_builder import load_local_graph


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_KG_DIR = WORKSPACE_ROOT / "data" / "processed" / "enterprise_kg"


def _graph(kg_dir: Path | str = DEFAULT_KG_DIR):
    kg_dir = Path(kg_dir)
    return load_local_graph(kg_dir / "nodes.jsonl", kg_dir / "relations.jsonl")


def enterprise_kg_query(
    entity: str,
    relation_type: str | None = None,
    depth: int = 2,
    kg_dir: Path | str = DEFAULT_KG_DIR,
) -> dict[str, Any]:
    """Query Enterprise KG around an entity.

    Returns a normalized graph payload with nodes, relations, and path evidence.
    """
    return _graph(kg_dir).neighborhood(entity=entity, relation_type=relation_type, depth=depth)


def get_customer_graph(customer_id: str, kg_dir: Path | str = DEFAULT_KG_DIR) -> dict[str, Any]:
    return enterprise_kg_query(customer_id, depth=2, kg_dir=kg_dir)


def get_product_dependency_graph(product_name: str, kg_dir: Path | str = DEFAULT_KG_DIR) -> dict[str, Any]:
    return enterprise_kg_query(
        product_name,
        relation_type="PRODUCT_DEPENDS_ON_SERVICE",
        depth=2,
        kg_dir=kg_dir,
    )


def find_related_tickets(entity_name: str, kg_dir: Path | str = DEFAULT_KG_DIR) -> dict[str, Any]:
    graph = enterprise_kg_query(entity_name, depth=3, kg_dir=kg_dir)
    ticket_ids = {node["node_id"] for node in graph["nodes"] if node.get("type") == "SupportTicket"}
    graph["related_ticket_ids"] = sorted(ticket_ids)
    return graph


def find_owner_team(service_or_module: str, kg_dir: Path | str = DEFAULT_KG_DIR) -> dict[str, Any]:
    graph = enterprise_kg_query(service_or_module, depth=2, kg_dir=kg_dir)
    teams = {node["name"] for node in graph["nodes"] if node.get("type") == "Team"}
    graph["owner_team_candidates"] = sorted(teams)
    return graph


def trace_issue_impact(issue_id: str, kg_dir: Path | str = DEFAULT_KG_DIR) -> dict[str, Any]:
    graph = enterprise_kg_query(issue_id, depth=3, kg_dir=kg_dir)
    graph["impacted_customers"] = sorted(node["name"] for node in graph["nodes"] if node.get("type") == "Customer")
    graph["impacted_products"] = sorted(node["name"] for node in graph["nodes"] if node.get("type") == "Product")
    return graph
