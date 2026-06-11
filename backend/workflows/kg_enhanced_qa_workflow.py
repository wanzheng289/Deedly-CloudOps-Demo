from __future__ import annotations

from typing import Any

try:
    from project.backend.agents.tool_router import route_query
    from project.backend.knowledge_graph.kg_query_tool import enterprise_kg_query
    from project.backend.workflows.kg_rag_workflow import VectorRetriever, _format_citations, _format_graph_paths
except ModuleNotFoundError:
    from backend.agents.tool_router import route_query
    from backend.knowledge_graph.kg_query_tool import enterprise_kg_query
    from backend.workflows.kg_rag_workflow import VectorRetriever, _format_citations, _format_graph_paths


def _default_vector_retriever(query: str, top_k: int = 5) -> dict[str, Any]:
    try:
        from project.backend.rag.retriever import retrieve_documents
    except ModuleNotFoundError:
        from backend.rag.retriever import retrieve_documents
    return retrieve_documents(query, top_k=top_k)


def run_kg_enhanced_qa_workflow(
    query: str,
    *,
    vector_retriever: VectorRetriever | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Answer enterprise questions with both document citations and KG paths."""
    decision = route_query(query)
    vector_retriever = vector_retriever or _default_vector_retriever
    vector_payload = vector_retriever(query, top_k)
    citations = _format_citations(vector_payload.get("docs", []), limit=top_k)

    graph_payloads = []
    graph_paths: list[str] = []
    entities = decision.entity_candidates or [query]
    for entity in entities[:3]:
        graph = enterprise_kg_query(entity, depth=2)
        graph_payloads.append(graph)
        graph_paths.extend(_format_graph_paths(graph, limit=5))

    answer = (
        "已结合企业文档和企业知识图谱生成答案草稿。"
        "请优先依据 citations 中的原文片段回答事实性内容，并用 graph_paths 解释实体关系、责任团队或影响范围。"
    )
    if citations:
        answer += f" 首要引用文档：《{citations[0]['title']}》。"
    if graph_paths:
        answer += f" 关键图谱路径：{graph_paths[0]}。"

    return {
        "workflow": "kg_enhanced_qa_workflow",
        "query": query,
        "plan": [
            {"step": "search_enterprise_kb", "status": "completed" if citations else "empty"},
            {"step": "enterprise_kg_query", "status": "completed" if graph_paths else "empty"},
            {"step": "compose_answer_with_citations_and_paths", "status": "completed"},
        ],
        "answer": answer,
        "citations": citations,
        "graph_paths": graph_paths[:12],
        "kg_graphs": graph_payloads,
        "vector_rag": vector_payload,
        "open_questions": [
            "需要确认引用文档是否为最新版本。",
            "需要确认图谱路径是否覆盖所有相关实体。",
        ],
    }
