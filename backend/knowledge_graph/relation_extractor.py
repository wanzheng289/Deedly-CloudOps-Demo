"""Rule-based relation extraction for Enterprise KG."""
from __future__ import annotations

from typing import Any

try:
    from project.backend.knowledge_graph.schema import KGNode, KGRelation, NodeType, RelationType
except ModuleNotFoundError:
    from backend.knowledge_graph.schema import KGNode, KGRelation, NodeType, RelationType


def _first(nodes: list[KGNode], node_type: NodeType) -> KGNode | None:
    for node in nodes:
        if node.type == node_type:
            return node
    return None


def _all(nodes: list[KGNode], node_type: NodeType) -> list[KGNode]:
    return [node for node in nodes if node.type == node_type]


def _rel(source: KGNode | None, relation_type: RelationType, target: KGNode | None, properties: dict[str, Any] | None = None) -> KGRelation | None:
    if not source or not target or source.node_id == target.node_id:
        return None
    return KGRelation(
        source_id=source.node_id,
        target_id=target.node_id,
        type=relation_type,
        properties=properties or {},
    )


def _dedupe(relations: list[KGRelation | None]) -> list[KGRelation]:
    merged: dict[tuple[str, str, str], KGRelation] = {}
    for relation in relations:
        if relation is None:
            continue
        key = (relation.source_id, relation.target_id, relation.type.value)
        existing = merged.get(key)
        if not existing:
            merged[key] = relation
            continue
        existing.properties.update({k: v for k, v in relation.properties.items() if v not in (None, "", [], {})})
    return list(merged.values())


def extract_customer_support_relations(record: dict[str, Any], nodes: list[KGNode]) -> list[KGRelation]:
    customer = _first(nodes, NodeType.CUSTOMER)
    ticket = _first(nodes, NodeType.SUPPORT_TICKET)
    product = _first(nodes, NodeType.PRODUCT)
    issue = _first(nodes, NodeType.ISSUE)
    faq = _first(nodes, NodeType.FAQ)
    agent = _first(nodes, NodeType.AGENT)
    properties = {
        "source": "customer_support",
        "ticket_id": record.get("ticket_id") or record.get("conv_id"),
        "priority": record.get("priority"),
        "status": record.get("status"),
    }
    return _dedupe(
        [
            _rel(customer, RelationType.CUSTOMER_OPENED_TICKET, ticket, properties),
            _rel(ticket, RelationType.TICKET_MENTIONS_PRODUCT, product, properties),
            _rel(ticket, RelationType.TICKET_HAS_ISSUE, issue, properties),
            _rel(ticket, RelationType.TICKET_HANDLED_BY_AGENT, agent, properties),
            _rel(customer, RelationType.CUSTOMER_USES_PRODUCT, product, {"source": "customer_support"}),
            _rel(faq, RelationType.FAQ_ANSWERS_ISSUE_TYPE, issue, {"source": "customer_support"}),
        ]
    )


def extract_document_relations(record: dict[str, Any], nodes: list[KGNode]) -> list[KGRelation]:
    document = _first(nodes, NodeType.DOCUMENT)
    source = _first(nodes, NodeType.SOURCE)
    relations: list[KGRelation | None] = [
        _rel(document, RelationType.DOCUMENT_FROM_SOURCE, source, {"source": "enterprise_rag_bench"})
    ]

    for product in _all(nodes, NodeType.PRODUCT):
        relations.append(_rel(document, RelationType.DOCUMENT_EXPLAINS_PRODUCT, product, {"source": "document_rule"}))
    for module in _all(nodes, NodeType.MODULE):
        relations.append(_rel(document, RelationType.DOCUMENT_EXPLAINS_MODULE, module, {"source": "document_rule"}))
    for service in _all(nodes, NodeType.SERVICE):
        relations.append(_rel(document, RelationType.DOCUMENT_MENTIONS_SERVICE, service, {"source": "document_rule"}))
    for team in _all(nodes, NodeType.TEAM):
        relations.append(_rel(document, RelationType.DOCUMENT_MENTIONS_TEAM, team, {"source": "document_rule"}))
        for service in _all(nodes, NodeType.SERVICE)[:5]:
            relations.append(_rel(team, RelationType.TEAM_OWNS_SERVICE, service, {"source": "document_owner_hint"}))
    for service in _all(nodes, NodeType.SERVICE):
        for env in _all(nodes, NodeType.DEPLOYMENT_ENV):
            relations.append(_rel(service, RelationType.SERVICE_RUNS_IN_ENV, env, {"source": "document_rule"}))
    for product in _all(nodes, NodeType.PRODUCT):
        for service in _all(nodes, NodeType.SERVICE)[:5]:
            relations.append(_rel(product, RelationType.PRODUCT_DEPENDS_ON_SERVICE, service, {"source": "document_title_hint"}))
    for module in _all(nodes, NodeType.MODULE):
        for version in _all(nodes, NodeType.VERSION):
            relations.append(_rel(module, RelationType.ISSUE_RELATED_TO_VERSION, version, {"source": "document_rule"}))

    return _dedupe(relations)


def extract_enterprise_relations(record: dict[str, Any], nodes: list[KGNode]) -> list[KGRelation]:
    """Extract enterprise KG relations from one normalized record and its nodes."""
    if record.get("ticket_id") or record.get("conv_id"):
        return extract_customer_support_relations(record, nodes)
    return extract_document_relations(record, nodes)


def relation_to_dict(relation: KGRelation) -> dict[str, Any]:
    return relation.dict() if hasattr(relation, "dict") else relation.model_dump()
