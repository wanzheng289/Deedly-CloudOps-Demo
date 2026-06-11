from __future__ import annotations

import re
from dataclasses import dataclass, field


CUSTOMER_KEYWORDS = (
    "客户",
    "之前",
    "历史",
    "工单",
    "反馈",
    "升级",
    "escalation",
    "ticket",
    "customer",
    "history",
    "previous",
)
KG_KEYWORDS = (
    "谁负责",
    "影响范围",
    "依赖",
    "关联",
    "模块",
    "团队",
    "owner",
    "impact",
    "dependency",
    "related",
    "module",
    "team",
    "graph",
)
VECTOR_KEYWORDS = (
    "文档",
    "怎么说",
    "支持哪些",
    "配置",
    "部署",
    "步骤",
    "api",
    "限制",
    "runbook",
    "document",
    "docs",
    "configure",
    "deploy",
    "support",
    "limit",
)
REPLY_KEYWORDS = ("回复", "生成回复", "草稿", "reply", "draft", "respond")
CUSTOMER_ID_RE = re.compile(r"\bCust[A-Z0-9]+\b", re.IGNORECASE)
SERVICE_RE = re.compile(r"\b[a-z][a-z0-9]+(?:-[a-z0-9]+)+\b")


@dataclass
class ToolRouteDecision:
    query: str
    customer_id: str | None = None
    entity_candidates: list[str] = field(default_factory=list)
    use_customer_profile: bool = False
    use_customer_tickets: bool = False
    use_enterprise_kg: bool = False
    use_vector_rag: bool = False
    draft_customer_reply: bool = False
    tool_sequence: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "customer_id": self.customer_id,
            "entity_candidates": self.entity_candidates,
            "use_customer_profile": self.use_customer_profile,
            "use_customer_tickets": self.use_customer_tickets,
            "use_enterprise_kg": self.use_enterprise_kg,
            "use_vector_rag": self.use_vector_rag,
            "draft_customer_reply": self.draft_customer_reply,
            "tool_sequence": self.tool_sequence,
            "reasons": self.reasons,
        }


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    text_l = text.lower()
    return any(keyword.lower() in text_l for keyword in keywords)


def _extract_customer_id(query: str) -> str | None:
    match = CUSTOMER_ID_RE.search(query)
    return match.group(0) if match else None


def _extract_entity_candidates(query: str, customer_id: str | None) -> list[str]:
    candidates: list[str] = []
    if customer_id:
        candidates.append(customer_id)
    candidates.extend(SERVICE_RE.findall(query))
    for token in ("SSO", "API", "GPU", "SLA", "KYC", "Exam", "Billing", "VPN"):
        if token.lower() in query.lower():
            candidates.append(token)
    deduped = []
    seen = set()
    for item in candidates:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def route_query(query: str, customer_id: str | None = None) -> ToolRouteDecision:
    """Route a user query to KG, vector RAG, and customer-memory tools."""
    explicit_customer_id = customer_id or _extract_customer_id(query)
    has_customer_need = bool(explicit_customer_id) or _contains_any(query, CUSTOMER_KEYWORDS)
    has_kg_need = _contains_any(query, KG_KEYWORDS)
    has_vector_need = _contains_any(query, VECTOR_KEYWORDS)
    has_reply_need = _contains_any(query, REPLY_KEYWORDS)
    is_combo = has_customer_need and (has_vector_need or has_kg_need or has_reply_need)

    decision = ToolRouteDecision(
        query=query,
        customer_id=explicit_customer_id,
        entity_candidates=_extract_entity_candidates(query, explicit_customer_id),
        use_customer_profile=has_customer_need,
        use_customer_tickets=has_customer_need,
        use_enterprise_kg=has_kg_need or is_combo,
        use_vector_rag=has_vector_need or is_combo,
        draft_customer_reply=has_reply_need or is_combo,
    )

    if has_customer_need:
        decision.reasons.append("customer_context_keywords_or_customer_id")
        decision.tool_sequence.extend(["get_customer_profile", "search_customer_tickets"])
    if decision.use_enterprise_kg:
        decision.reasons.append("relationship_or_impact_keywords")
        decision.tool_sequence.append("enterprise_kg_query")
    if decision.use_vector_rag:
        decision.reasons.append("document_or_configuration_keywords")
        decision.tool_sequence.append("search_enterprise_kb")
    if decision.draft_customer_reply:
        decision.reasons.append("reply_generation_or_combo_task")
        decision.tool_sequence.append("draft_customer_reply")

    # De-duplicate while preserving order.
    seen = set()
    decision.tool_sequence = [tool for tool in decision.tool_sequence if not (tool in seen or seen.add(tool))]
    return decision
