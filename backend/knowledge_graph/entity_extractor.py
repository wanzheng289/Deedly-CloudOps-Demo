"""Rule-based entity extraction for the Enterprise KG."""
from __future__ import annotations

import re
from typing import Any

try:
    from project.backend.knowledge_graph.schema import KGNode, NodeType
except ModuleNotFoundError:
    from backend.knowledge_graph.schema import KGNode, NodeType


SERVICE_PATTERNS = (
    r"\b[a-z][a-z0-9]+(?:-[a-z0-9]+)+\b",
    r"\b[A-Z][A-Za-z0-9]+(?:Service|API|Gateway|Worker|Pipeline|Store)\b",
)
MODULE_KEYWORDS = (
    "auth",
    "sso",
    "billing",
    "deployment",
    "observability",
    "telemetry",
    "runtime",
    "inference",
    "dashboard",
    "alerting",
    "rollback",
    "upgrade",
    "terraform",
    "helm",
    "kubernetes",
)
ENV_KEYWORDS = ("prod", "production", "staging", "dev", "qa", "us-east", "us-west", "eu-west", "region")
TEAM_RE = re.compile(r"(?:Owners?|Team|Primary users):\s*([^\n]+)", re.IGNORECASE)
CHANNEL_RE = re.compile(r"#[a-z][a-z0-9_-]+", re.IGNORECASE)
VERSION_RE = re.compile(r"\b(?:v\d+(?:\.\d+){0,3}|\d+\.\d+\.\d+|REVISION|runtime_build_id|model_version)\b")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", _clean(value).lower()).strip("-")
    return slug[:160] or "unknown"


def _node(node_type: NodeType, name: str, properties: dict[str, Any] | None = None) -> KGNode | None:
    name = _clean(name)
    if not name:
        return None
    return KGNode(
        node_id=f"{node_type.value.lower()}:{_slug(name)}",
        type=node_type,
        name=name,
        properties=properties or {},
    )


def _dedupe(nodes: list[KGNode | None]) -> list[KGNode]:
    merged: dict[str, KGNode] = {}
    for node in nodes:
        if node is None:
            continue
        existing = merged.get(node.node_id)
        if not existing:
            merged[node.node_id] = node
            continue
        existing.properties.update({k: v for k, v in node.properties.items() if v not in (None, "", [], {})})
    return list(merged.values())


def extract_customer_support_entities(record: dict[str, Any]) -> list[KGNode]:
    """Extract Customer/Product/Ticket/Issue/Agent nodes from a support ticket."""
    nodes: list[KGNode | None] = []
    customer_id = _clean(record.get("customer_id") or record.get("customer_name"))
    ticket_id = _clean(record.get("ticket_id") or record.get("conv_id"))
    product = _clean(record.get("product"))
    issue_type = _clean(record.get("issue_type"))
    agent_name = _clean(record.get("agent_name"))

    nodes.append(
        _node(
            NodeType.CUSTOMER,
            customer_id,
            {
                "industry": record.get("industry"),
                "channel": record.get("channel"),
                "source": "customer_support",
            },
        )
    )
    nodes.append(_node(NodeType.PRODUCT, product, {"source": "customer_support"}))
    nodes.append(
        _node(
            NodeType.SUPPORT_TICKET,
            ticket_id,
            {
                "status": record.get("status"),
                "priority": record.get("priority"),
                "summary": record.get("summary"),
                "overall_sentiment": record.get("overall_sentiment"),
                "overall_urgency": record.get("overall_urgency"),
                "last_message_at": record.get("last_message_at"),
                "source": "customer_support",
            },
        )
    )
    nodes.append(_node(NodeType.ISSUE, issue_type, {"source": "customer_support"}))
    nodes.append(_node(NodeType.FAQ, issue_type, {"source": "customer_support", "product": product}))
    nodes.append(_node(NodeType.AGENT, agent_name, {"source": "customer_support"}))

    return _dedupe(nodes)


def extract_document_entities(record: dict[str, Any]) -> list[KGNode]:
    """Extract Document/Source/Product/Module/Service/Team/Version nodes from a document."""
    doc_id = _clean(record.get("doc_id") or record.get("id"))
    title = _clean(record.get("title")) or doc_id
    source_type = _clean(record.get("source_type") or (record.get("metadata") or {}).get("source_type"))
    content = _clean(record.get("content") or record.get("text"))
    text = f"{title}\n{content}"
    lower_text = text.lower()

    nodes: list[KGNode | None] = [
        KGNode(
            node_id=f"document:{_slug(doc_id or title)}",
            type=NodeType.DOCUMENT,
            name=title,
            properties={
                "doc_id": doc_id,
                "source_type": source_type,
                "title": title,
                "content_preview": content[:500],
                "source": "enterprise_rag_bench",
            },
        ),
        _node(NodeType.SOURCE, source_type, {"source": "enterprise_rag_bench"}),
    ]

    for keyword in MODULE_KEYWORDS:
        if keyword in lower_text:
            nodes.append(_node(NodeType.MODULE, keyword, {"source": "document_keyword"}))

    for pattern in SERVICE_PATTERNS:
        for match in re.findall(pattern, text):
            nodes.append(_node(NodeType.SERVICE, match, {"source": "document_regex"}))

    for env in ENV_KEYWORDS:
        if env in lower_text:
            nodes.append(_node(NodeType.DEPLOYMENT_ENV, env, {"source": "document_keyword"}))

    for version in VERSION_RE.findall(text):
        nodes.append(_node(NodeType.VERSION, version, {"source": "document_regex"}))

    for match in TEAM_RE.findall(text):
        for item in re.split(r"[,/&]| and ", match):
            item = _clean(item).strip("-:•")
            if 2 <= len(item) <= 80:
                nodes.append(_node(NodeType.TEAM, item, {"source": "document_owner_line"}))

    for channel in CHANNEL_RE.findall(text):
        nodes.append(_node(NodeType.TEAM, channel, {"source": "document_channel"}))

    if "sla" in lower_text or "p95" in lower_text or "p99" in lower_text:
        nodes.append(_node(NodeType.SLA, f"{title} SLA", {"source": "document_keyword"}))

    # Treat title token before colon as a product/service family hint when present.
    if ":" in title:
        family = title.split(":", 1)[1].split("(", 1)[0].strip()
        for token in re.split(r"/|,| and ", family):
            token = _clean(token)
            if 2 <= len(token) <= 80:
                nodes.append(_node(NodeType.PRODUCT, token, {"source": "document_title"}))

    return _dedupe(nodes)


def extract_enterprise_entities(record: dict[str, Any]) -> list[KGNode]:
    """Extract enterprise KG nodes from one normalized record."""
    if record.get("ticket_id") or record.get("conv_id"):
        return extract_customer_support_entities(record)
    return extract_document_entities(record)


def node_to_dict(node: KGNode) -> dict[str, Any]:
    return node.dict() if hasattr(node, "dict") else node.model_dump()
