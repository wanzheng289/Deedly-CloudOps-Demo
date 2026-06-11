from __future__ import annotations

import re
from typing import Any

try:
    from project.backend.knowledge_graph.kg_query_tool import find_related_tickets
    from project.backend.memory.store import default_store
except ModuleNotFoundError:
    from backend.knowledge_graph.kg_query_tool import find_related_tickets
    from backend.memory.store import default_store


HIGH_KEYWORDS = ("urgent", "outage", "down", "cannot login", "production", "prod", "blocked", "sev", "宕机", "无法登录", "紧急", "生产")
LOW_KEYWORDS = ("question", "how to", "docs", "文档", "咨询", "怎么")
NEGATIVE_KEYWORDS = ("angry", "frustrated", "bad", "broken", "not working", "cannot", "failed", "urgent", "无法", "失败", "不满", "紧急")
POSITIVE_KEYWORDS = ("thanks", "resolved", "works", "感谢", "已解决")
INTENT_RULES = {
    "access_issue": ("login", "sso", "access", "无法登录", "权限"),
    "deployment_issue": ("deploy", "deployment", "rollback", "helm", "kubernetes", "部署", "回滚"),
    "billing_issue": ("billing", "invoice", "payment", "账单", "付款"),
    "how_to_question": ("how to", "docs", "configure", "怎么", "配置"),
}
CUSTOMER_ID_RE = re.compile(r"\bCust[A-Z0-9]+\b", re.IGNORECASE)


def classify_intent(ticket_text: str) -> str:
    text = ticket_text.lower()
    for intent, keywords in INTENT_RULES.items():
        if any(keyword.lower() in text for keyword in keywords):
            return intent
    return "general_support"


def detect_sentiment(ticket_text: str) -> str:
    text = ticket_text.lower()
    if any(keyword.lower() in text for keyword in NEGATIVE_KEYWORDS):
        return "negative"
    if any(keyword.lower() in text for keyword in POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def assign_priority(ticket_text: str, sentiment: str, related_ticket_count: int = 0) -> str:
    text = ticket_text.lower()
    if any(keyword.lower() in text for keyword in HIGH_KEYWORDS):
        return "high"
    if sentiment == "negative" and related_ticket_count >= 2:
        return "high"
    if any(keyword.lower() in text for keyword in LOW_KEYWORDS):
        return "low"
    if sentiment == "negative" or related_ticket_count >= 1:
        return "medium"
    return "medium"


def _extract_customer_id(ticket_text: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    match = CUSTOMER_ID_RE.search(ticket_text)
    return match.group(0) if match else None


def _extract_entity(ticket_text: str, product: str | None = None, issue_type: str | None = None) -> str:
    if product:
        return product
    if issue_type:
        return issue_type
    for token in ("SSO", "API", "GPU", "Billing", "KYC", "Exam", "perf-canary"):
        if token.lower() in ticket_text.lower():
            return token
    return ticket_text[:80]


def run_ticket_priority_workflow(
    ticket_text: str,
    *,
    customer_id: str | None = None,
    product: str | None = None,
    issue_type: str | None = None,
) -> dict[str, Any]:
    """Classify support ticket priority and produce next actions."""
    resolved_customer_id = _extract_customer_id(ticket_text, customer_id)
    intent = classify_intent(ticket_text)
    sentiment = detect_sentiment(ticket_text)
    related_tickets = []
    if resolved_customer_id:
        related_tickets = default_store.search_customer_tickets(resolved_customer_id, query=ticket_text, limit=5)
    graph = find_related_tickets(_extract_entity(ticket_text, product=product, issue_type=issue_type))
    related_ticket_ids = graph.get("related_ticket_ids", [])[:10]
    priority = assign_priority(ticket_text, sentiment, related_ticket_count=len(related_tickets) + len(related_ticket_ids))

    next_steps = [
        "确认客户环境、版本、报错截图和复现步骤。",
        "检索相关产品文档并附上可执行处理步骤。",
    ]
    if priority == "high":
        next_steps.insert(0, "创建高优先级跟进并通知对应 owner/on-call。")
    if intent == "deployment_issue":
        next_steps.append("检查最近部署、回滚记录和变更窗口。")
    if intent == "access_issue":
        next_steps.append("核对身份映射、权限、订阅/课程 entitlement 同步状态。")

    return {
        "workflow": "ticket_priority_workflow",
        "ticket_text": ticket_text,
        "plan": [
            {"step": "classify_intent", "status": "completed"},
            {"step": "detect_sentiment", "status": "completed"},
            {"step": "assign_priority", "status": "completed"},
            {"step": "find_related_tickets", "status": "completed"},
            {"step": "generate_next_steps", "status": "completed"},
        ],
        "intent": intent,
        "sentiment": sentiment,
        "priority": priority,
        "customer_id": resolved_customer_id,
        "related_customer_tickets": related_tickets,
        "related_graph_ticket_ids": related_ticket_ids,
        "graph": graph,
        "next_steps": next_steps,
    }
