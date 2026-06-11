from __future__ import annotations

import json
from typing import Any, Callable

try:
    from project.backend.agents.tool_router import ToolRouteDecision, route_query
    from project.backend.knowledge_graph.kg_query_tool import enterprise_kg_query
    from project.backend.tools.customer_ops_tools import (
        _get_customer_profile_impl,
        _search_customer_tickets_impl,
    )
except ModuleNotFoundError:
    from backend.agents.tool_router import ToolRouteDecision, route_query
    from backend.knowledge_graph.kg_query_tool import enterprise_kg_query
    from backend.tools.customer_ops_tools import (
        _get_customer_profile_impl,
        _search_customer_tickets_impl,
    )


VectorRetriever = Callable[[str, int], dict[str, Any]]


def _default_vector_retriever(query: str, top_k: int = 5) -> dict[str, Any]:
    try:
        from project.backend.rag.retriever import retrieve_documents
    except ModuleNotFoundError:
        from backend.rag.retriever import retrieve_documents

    return retrieve_documents(query, top_k=top_k)


def _parse_json_result(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": payload}


def _format_graph_paths(graph: dict[str, Any], limit: int = 8) -> list[str]:
    nodes = {node.get("node_id"): node for node in graph.get("nodes", [])}
    paths = []
    for relation in graph.get("relations", [])[:limit]:
        source = nodes.get(relation.get("source_id"), {})
        target = nodes.get(relation.get("target_id"), {})
        source_label = f"{source.get('type', 'Node')}({source.get('name', relation.get('source_id'))})"
        target_label = f"{target.get('type', 'Node')}({target.get('name', relation.get('target_id'))})"
        paths.append(f"{source_label} --{relation.get('type')}--> {target_label}")
    return paths


def _format_citations(docs: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    citations = []
    for idx, doc in enumerate(docs[:limit], 1):
        citations.append(
            {
                "rank": idx,
                "title": doc.get("title") or doc.get("filename") or "Unknown",
                "doc_id": doc.get("doc_id") or doc.get("chunk_id") or "",
                "source_type": doc.get("source_type") or doc.get("file_type") or "unknown",
                "text_preview": (doc.get("text") or "")[:260],
            }
        )
    return citations


def _draft_customer_reply(
    query: str,
    profile: dict[str, Any] | None,
    tickets: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    graph_paths: list[str],
) -> str:
    customer_name = (profile or {}).get("customer_id") or "该客户"
    products = ", ".join((profile or {}).get("products") or []) or "相关产品"
    latest_ticket = tickets[0] if tickets else {}
    issue = latest_ticket.get("issue_type") or "当前问题"
    doc_hint = citations[0]["title"] if citations else "当前知识库"
    graph_hint = graph_paths[0] if graph_paths else "暂无明确图谱路径"
    return (
        f"建议回复：已结合 {customer_name} 的历史记录、{products} 相关知识和企业图谱进行核对。"
        f"客户最近相关问题是 {issue}；可先说明我们已看到历史上下文，并基于《{doc_hint}》给出处理建议。"
        f"内部依据包括图谱路径：{graph_hint}。如需对外发送，建议补充具体配置值、环境和当前报错截图。"
    )


def run_kg_rag_workflow(
    query: str,
    customer_id: str | None = None,
    *,
    vector_retriever: VectorRetriever | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Coordinate customer memory, Enterprise KG, and vector RAG evidence."""
    decision: ToolRouteDecision = route_query(query, customer_id=customer_id)
    vector_retriever = vector_retriever or _default_vector_retriever

    profile_payload: dict[str, Any] | None = None
    tickets_payload: dict[str, Any] | None = None
    graph_payloads: list[dict[str, Any]] = []
    vector_payload: dict[str, Any] = {"docs": [], "meta": {"retrieval_mode": "skipped"}}

    if decision.use_customer_profile and decision.customer_id:
        profile_payload = _parse_json_result(_get_customer_profile_impl(decision.customer_id))
    if decision.use_customer_tickets and decision.customer_id:
        tickets_payload = _parse_json_result(_search_customer_tickets_impl(decision.customer_id, query=query, limit=top_k))
    if decision.use_enterprise_kg:
        entities = decision.entity_candidates or ([decision.customer_id] if decision.customer_id else [query])
        for entity in entities[:3]:
            graph_payloads.append(enterprise_kg_query(entity, depth=2))
    if decision.use_vector_rag:
        try:
            vector_payload = vector_retriever(query, top_k)
        except Exception as exc:
            vector_payload = {"docs": [], "meta": {"retrieval_mode": "failed", "error": str(exc)}}

    tickets = (tickets_payload or {}).get("tickets", [])
    profile = (profile_payload or {}).get("profile")
    docs = vector_payload.get("docs", [])
    citations = _format_citations(docs, limit=top_k)
    graph_paths: list[str] = []
    for graph in graph_payloads:
        graph_paths.extend(_format_graph_paths(graph))
    graph_paths = graph_paths[:12]

    answer = _draft_customer_reply(query, profile, tickets, citations, graph_paths) if decision.draft_customer_reply else (
        "已完成证据检索。请参考 citations 和 graph_paths 字段查看文档证据与图谱路径。"
    )
    open_questions = [
        "需要确认客户当前环境、版本、报错信息是否与历史工单一致。",
        "需要确认引用文档是否覆盖最新产品策略或部署限制。",
    ]
    if not citations and decision.use_vector_rag:
        open_questions.append("向量检索未返回文档片段，需要检查索引或改写查询。")
    if not graph_paths and decision.use_enterprise_kg:
        open_questions.append("图谱未返回明确路径，需要确认实体名称或补充 KG 抽取规则。")

    return {
        "query": query,
        "route": decision.to_dict(),
        "answer": answer,
        "citations": citations,
        "graph_paths": graph_paths,
        "customer_profile": profile_payload,
        "customer_tickets": tickets_payload,
        "kg_graphs": graph_payloads,
        "vector_rag": vector_payload,
        "open_questions": open_questions,
    }
