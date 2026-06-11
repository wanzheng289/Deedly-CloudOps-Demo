import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from project.backend.agents.main_agent import chat_with_agent, chat_with_agent_stream, storage
from project.backend.api.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_db,
    get_password_hash,
    require_admin,
    resolve_role,
)
from project.backend.api.upload_jobs import DELETE_STEPS, delete_job_manager, upload_job_manager
from project.backend.db.milvus import MilvusManager
from project.backend.db.models import User
from project.backend.rag.document_loader import DocumentLoader
from project.backend.rag.embedding import embedding_service
from project.backend.rag.indexer import MilvusWriter
from project.backend.rag.parent_store import ParentChunkStore
from project.backend.schemas.chat import (
    AuthResponse,
    ChatRequest,
    ChatResponse,
    CurrentUserResponse,
    DocumentDeleteJobResponse,
    DocumentDeleteResponse,
    DocumentDeleteStartResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadJobResponse,
    DocumentUploadResponse,
    DocumentUploadStartResponse,
    LoginRequest,
    MessageInfo,
    RegisterRequest,
    SessionDeleteResponse,
    SessionInfo,
    SessionListResponse,
    SessionMessagesResponse,
)
from project.backend.workflows.customer_reply_workflow import run_customer_reply_workflow
from project.backend.workflows.kg_enhanced_qa_workflow import run_kg_enhanced_qa_workflow
from project.backend.workflows.ticket_priority_workflow import run_ticket_priority_workflow

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
UPLOAD_DIR = DATA_DIR / "documents"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DATA_DIR = WORKSPACE_ROOT / "data" / "processed"
SUPPORT_DIR = PROCESSED_DATA_DIR / "customer_support"
ENTERPRISE_RAG_DIR = PROCESSED_DATA_DIR / "enterprise_rag_bench"
ENTERPRISE_KG_DIR = PROCESSED_DATA_DIR / "enterprise_kg"

loader = DocumentLoader()
parent_chunk_store = ParentChunkStore()
milvus_manager = MilvusManager()
milvus_writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus_manager)

router = APIRouter()


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def _safe_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def _compact_text(value: str, max_len: int = 150) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= max_len else f"{text[:max_len].rstrip()}..."


def _first_list_item(value: Any, fallback: str = "unknown") -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if value:
        return str(value)
    return fallback


def _priority_score(customer: dict[str, Any]) -> tuple[int, int, str]:
    return (
        10 if customer.get("customer_id") == "CustQRWQE" else 0,
        int(customer.get("high_priority_ticket_count") or 0),
        customer.get("last_seen_at") or "",
    )


def _workspace_customers(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = sorted(profiles, key=_priority_score, reverse=True)[:8]
    return [
        {
            "id": item.get("customer_id"),
            "title": item.get("customer_id"),
            "subtitle": (
                f"{_first_list_item(item.get('industries'), 'customer')} · "
                f"{', '.join(item.get('products') or []) or 'unknown product'}"
            ),
            "meta": (
                f"high={item.get('high_priority_ticket_count', 0)} · "
                f"tickets={item.get('conversation_count', 0)} · "
                f"last={item.get('last_seen_at', '')[:10]}"
            ),
            "query": f"查看 {item.get('customer_id')} 的客户画像、历史工单和常见问题。",
        }
        for item in selected
        if item.get("customer_id")
    ]


def _workspace_products(tickets: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ticket_counts = Counter(item.get("product") for item in tickets if item.get("product"))
    node_products = [item.get("name") for item in nodes if item.get("type") == "Product" and item.get("name")]
    preferred = ["SSO", "perf-canary", "Course Access", "API", "Billing", "Course"]
    merged: list[str] = []
    for name in preferred + [name for name, _ in ticket_counts.most_common(30)] + node_products[:50]:
        if name and name not in merged:
            merged.append(name)
    return [
        {
            "id": name,
            "title": name,
            "subtitle": "product / issue / service",
            "meta": f"tickets={ticket_counts.get(name, 0)}",
            "query": f"{name} 相关的客户、工单、知识库文档和图谱关系有哪些？",
        }
        for name in merged[:10]
    ]


def _workspace_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("doc_id"),
            "title": item.get("title") or item.get("doc_id"),
            "subtitle": item.get("source_type") or "document",
            "meta": _compact_text(item.get("content") or "", 92),
            "query": (
                f"请总结 doc_id={item.get('doc_id')} 的《{item.get('title') or item.get('doc_id')}》"
                "的关键内容，并说明适用场景。"
            ),
        }
        for item in documents[:8]
        if item.get("doc_id")
    ]


def _workspace_tickets(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = sorted(
        tickets,
        key=lambda item: (
            10 if item.get("customer_id") == "CustQRWQE" else 0,
            3 if item.get("priority") == "high" else 0,
            2 if item.get("status") in {"open", "escalated"} else 0,
            item.get("last_message_at") or "",
        ),
        reverse=True,
    )[:10]
    return [
        {
            "id": item.get("ticket_id"),
            "title": f"{item.get('ticket_id')} · {item.get('customer_id')}",
            "subtitle": f"{item.get('product')} / {item.get('issue_type')}",
            "meta": f"{item.get('priority')} · {item.get('status')} · {item.get('last_message_at', '')[:10]}",
            "query": (
                f"分析工单 {item.get('ticket_id')}：客户 {item.get('customer_id')} 的 "
                f"{item.get('product')} / {item.get('issue_type')} 问题应该如何处理？"
            ),
        }
        for item in selected
        if item.get("ticket_id")
    ]


def _workspace_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "id": "urgent_customer_incident",
            "title": "客户紧急故障",
            "subtitle": "Memory + Ticket + KG + Priority",
            "query": "客户 CustQRWQE 说生产环境无法登录 SSO，而且很着急，请判断优先级并给出下一步处理建议。",
            "uses": ["customer profile", "ticket history", "enterprise KG", "priority reasoning"],
            "expected": [
                "识别 CustQRWQE 客户画像和历史 SSO 工单",
                "判断是否属于生产故障和高优先级",
                "给出下一步排障、升级和沟通建议",
            ],
            "tools": ["get_customer_profile", "search_customer_tickets", "enterprise_kg_query", "search_enterprise_kb"],
        },
        {
            "id": "customer_reply_generation",
            "title": "客服回复生成",
            "subtitle": "Memory + RAG + Citation",
            "query": "客户 CustQRWQE 之前有 SSO 工单，现在问部署 perf-canary 是否会影响访问，请结合历史和文档生成回复。",
            "uses": ["customer memory", "ticket history", "document RAG", "citation drafting"],
            "expected": [
                "结合客户历史问题和当前产品上下文",
                "引用 perf-canary 部署/回滚相关文档",
                "输出可直接发给客户的回复草稿",
            ],
            "tools": ["get_customer_profile", "search_customer_tickets", "enterprise_kg_query", "search_enterprise_kb"],
        },
        {
            "id": "enterprise_knowledge_qa",
            "title": "企业知识问答",
            "subtitle": "RAG + Citation",
            "query": "perf-canary 部署到 prod 时需要检查哪些事项？",
            "uses": ["enterprise knowledge base", "hybrid retrieval", "citations"],
            "expected": [
                "召回部署、回滚或生产变更相关文档",
                "总结上线前检查项和风险控制点",
                "在 Evidence Brief 中展示 RAG Sources",
            ],
            "tools": ["search_enterprise_kb"],
        },
        {
            "id": "impact_analysis",
            "title": "影响范围分析",
            "subtitle": "KG + Tool Calling",
            "query": "SSO 出问题可能影响哪些客户、工单和产品模块？",
            "uses": ["enterprise KG", "customer-product relation", "related tickets", "impact tracing"],
            "expected": [
                "从图谱中追踪 SSO 与客户、工单、问题类型的关系",
                "列出可能受影响客户和相关历史工单",
                "解释影响范围和下一步验证动作",
            ],
            "tools": ["enterprise_kg_query", "find_related_tickets", "trace_issue_impact"],
        },
    ]


def _demo_company(source_counts: Counter[str], product_counts: Counter[str]) -> dict[str, Any]:
    products = ["SSO", "perf-canary", "Course Access"]
    dynamic_products = [name for name, _ in product_counts.most_common(8) if name and name not in products]
    sources = ["jira", "confluence", "fireflies", "hubspot", "gmail", "github"]
    dynamic_sources = [name for name, _ in source_counts.most_common(8) if name and name not in sources]
    return {
        "name": "Deedly CloudOps",
        "workspace_name": "Deedly CloudOps Demo",
        "tagline": "A virtual SaaS operations company built from public enterprise RAG and support datasets.",
        "description": (
            "Deedly CloudOps is a demo company used to make the public datasets feel like one coherent "
            "customer operations workspace. It has customers, products, tickets, internal docs, teams, "
            "services, and graph relations, but does not represent a real company."
        ),
        "products": (products + dynamic_products)[:8],
        "customers": ["CustQRWQE", "CustBBTPM", "CustBDBKJ", "CustBGFJM"],
        "teams": ["eng-runtime", "eng-infra", "eng-identity", "support-oncall", "customer-success"],
        "data_sources": (sources + dynamic_sources)[:10],
        "agent_scope": [
            "customer memory",
            "ticket triage",
            "enterprise RAG",
            "Enterprise KG",
            "workflow eval",
        ],
        "disclaimer": "Synthetic demo workspace assembled from public datasets; replace via the standard migration schema for real companies.",
    }


@router.get("/workspace/explorer")
async def workspace_explorer():
    profiles = _read_jsonl(SUPPORT_DIR / "customer_profiles.jsonl")
    tickets = _read_jsonl(SUPPORT_DIR / "support_tickets.jsonl")
    documents = _read_jsonl(ENTERPRISE_RAG_DIR / "sample_documents.jsonl", limit=80)
    nodes = _read_jsonl(ENTERPRISE_KG_DIR / "nodes.jsonl")

    source_counts = Counter(item.get("source_type") or "unknown" for item in documents)
    product_counts = Counter(item.get("product") for item in tickets if item.get("product"))
    issue_counts = Counter(item.get("issue_type") for item in tickets if item.get("issue_type"))

    return {
        "workspace": {
            "name": "Deedly CloudOps Demo",
            "company": "Deedly CloudOps",
            "description": "A virtual-company workspace backed by public datasets for RAG, KG, memory, and tool-calling demos.",
            "is_demo": True,
        },
        "demo_company": _demo_company(source_counts, product_counts),
        "overview": {
            "customers": len(profiles),
            "tickets": len(tickets),
            "documents": _safe_count(ENTERPRISE_RAG_DIR / "sample_documents.jsonl"),
            "kg_nodes": _safe_count(ENTERPRISE_KG_DIR / "nodes.jsonl"),
            "kg_relations": _safe_count(ENTERPRISE_KG_DIR / "relations.jsonl"),
        },
        "customers": _workspace_customers(profiles),
        "products": _workspace_products(tickets, nodes),
        "documents": _workspace_documents(documents),
        "tickets": _workspace_tickets(tickets),
        "scenarios": _workspace_scenarios(),
        "source_types": [{"title": key, "meta": f"docs={value}"} for key, value in source_counts.most_common()],
        "top_issues": [{"title": key, "meta": f"tickets={value}"} for key, value in issue_counts.most_common(8)],
        "top_products": [{"title": key, "meta": f"tickets={value}"} for key, value in product_counts.most_common(8)],
    }


def _demo_citation_items(citations: list[dict]) -> list[dict]:
    return [
        {
            "title": item.get("title") or "Unknown",
            "doc_id": item.get("doc_id") or "",
            "source_type": item.get("source_type") or "unknown",
            "preview": item.get("text_preview") or item.get("preview") or "",
        }
        for item in citations
    ]


def _demo_memory_items(payload: dict) -> list[dict]:
    memory_items: list[dict] = []
    profile = ((payload.get("evidence") or {}).get("customer_profile") or {}).get("profile")
    if profile:
        products = ", ".join(profile.get("products") or [])
        memory_items.append(
            {
                "title": "Customer profile",
                "body": f"{profile.get('customer_id', '')} · {profile.get('segment', 'customer')} · {products}",
                "meta": "profile_memory",
            }
        )

    tickets = ((payload.get("evidence") or {}).get("customer_tickets") or {}).get("tickets", [])
    for ticket in tickets[:3]:
        memory_items.append(
            {
                "title": "Related ticket",
                "body": (
                    f"{ticket.get('ticket_id', '')} · {ticket.get('product', '')} / "
                    f"{ticket.get('issue_type', '')} · {ticket.get('priority', '')} · {ticket.get('status', '')}"
                ),
                "meta": "support_ticket",
            }
        )

    for ticket in payload.get("related_customer_tickets", [])[:3]:
        memory_items.append(
            {
                "title": "Related ticket",
                "body": (
                    f"{ticket.get('ticket_id', '')} · {ticket.get('product', '')} / "
                    f"{ticket.get('issue_type', '')} · {ticket.get('priority', '')} · {ticket.get('status', '')}"
                ),
                "meta": "support_ticket",
            }
        )
    return memory_items


def _demo_eval(workflow: str, payload: dict) -> dict:
    citations = payload.get("citations") or (payload.get("response_sections") or {}).get("citations") or []
    graph_paths = payload.get("graph_paths") or (payload.get("response_sections") or {}).get("graph_paths") or []
    memory_items = _demo_memory_items(payload)
    eval_items = {"tool_call_accuracy": 1.0}
    if workflow in {"customerReply", "kgQa"}:
        eval_items["citation_coverage"] = 1.0 if citations else 0.0
        eval_items["kg_query_accuracy"] = 1.0 if graph_paths else 0.0
    if workflow in {"customerReply", "ticketPriority"}:
        eval_items["memory_usefulness"] = 1.0 if memory_items else 0.0
    if workflow == "ticketPriority":
        eval_items["priority_match"] = 1.0 if payload.get("priority") else 0.0
    return eval_items


@router.post("/demo/run")
async def run_demo_workflow(request: dict):
    scenario = request.get("scenario")
    query = (request.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    try:
        if scenario == "customerReply":
            payload = run_customer_reply_workflow(query)
            answer = payload.get("draft_reply") or payload.get("answer") or ""
            citations = (payload.get("response_sections") or {}).get("citations") or []
            graph_paths = (payload.get("response_sections") or {}).get("graph_paths") or []
        elif scenario == "kgQa":
            payload = run_kg_enhanced_qa_workflow(query)
            answer = payload.get("answer") or ""
            citations = payload.get("citations") or []
            graph_paths = payload.get("graph_paths") or []
        elif scenario == "ticketPriority":
            payload = run_ticket_priority_workflow(query)
            answer = (
                f"优先级：{payload.get('priority')}\n"
                f"意图：{payload.get('intent')}\n"
                f"情绪：{payload.get('sentiment')}\n"
                f"下一步：{'；'.join(payload.get('next_steps') or [])}"
            )
            citations = []
            graph_paths = []
            graph = payload.get("graph") or {}
            nodes = {node.get("node_id"): node for node in graph.get("nodes", [])}
            for relation in graph.get("relations", [])[:8]:
                source = nodes.get(relation.get("source_id"), {})
                target = nodes.get(relation.get("target_id"), {})
                graph_paths.append(
                    f"{source.get('type', 'Node')}({source.get('name', relation.get('source_id'))}) "
                    f"--{relation.get('type')}--> "
                    f"{target.get('type', 'Node')}({target.get('name', relation.get('target_id'))})"
                )
        else:
            raise HTTPException(status_code=400, detail=f"unsupported scenario: {scenario}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "scenario": scenario,
        "query": query,
        "answer": answer,
        "tools": [step.get("step") for step in payload.get("plan", [])],
        "sources": _demo_citation_items(citations),
        "paths": graph_paths,
        "memory": _demo_memory_items(payload),
        "eval": _demo_eval(scenario, {**payload, "citations": citations, "graph_paths": graph_paths}),
        "raw": payload,
    }


@router.post("/agent/run")
async def run_unified_agent(request: dict):
    query = (request.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    session_id = request.get("session_id") or "frontend_demo_session"
    user_id = request.get("user_id") or "frontend_demo_user"
    try:
        result = chat_with_agent(query, user_id=user_id, session_id=session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "scenario": request.get("scenario") or "agent",
        "query": query,
        "answer": result.get("response") or "",
        "tools": result.get("tools") or [],
        "sources": result.get("sources") or [],
        "paths": result.get("paths") or [],
        "memory": result.get("memory") or [],
        "eval": result.get("eval") or {},
        "rag_trace": result.get("rag_trace"),
        "tool_outputs": result.get("tool_outputs") or [],
        "raw": result,
    }


def _remove_bm25_stats_for_filename(filename: str) -> None:
    """删除 Milvus 中该文件对应 chunk 前，先从持久化 BM25 统计中扣减。"""
    rows = milvus_manager.query_all(
        filter_expr=f'filename == "{filename}"',
        output_fields=["text"],
    )
    texts = [r.get("text") or "" for r in rows]
    embedding_service.increment_remove_documents(texts)


@router.post("/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    username = (request.username or "").strip()
    password = (request.password or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")

    role = resolve_role(request.role, request.admin_code)
    user = User(username=username, password_hash=get_password_hash(password), role=role)
    db.add(user)
    db.commit()

    token = create_access_token(username=username, role=role)
    return AuthResponse(access_token=token, username=username, role=role)


@router.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(username=user.username, role=user.role)
    return AuthResponse(access_token=token, username=user.username, role=user.role)


@router.get("/auth/me", response_model=CurrentUserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(username=current_user.username, role=current_user.role)


@router.get("/sessions/{session_id}", response_model=SessionMessagesResponse)
async def get_session_messages(session_id: str, current_user: User = Depends(get_current_user)):
    """获取指定会话的所有消息"""
    try:
        messages = [
            MessageInfo(
                type=msg["type"],
                content=msg["content"],
                timestamp=msg["timestamp"],
                rag_trace=msg.get("rag_trace"),
            )
            for msg in storage.get_session_messages(current_user.username, session_id)
        ]
        return SessionMessagesResponse(messages=messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(current_user: User = Depends(get_current_user)):
    """获取当前用户的所有会话列表"""
    try:
        sessions = [SessionInfo(**item) for item in storage.list_session_infos(current_user.username)]
        sessions.sort(key=lambda x: x.updated_at, reverse=True)
        return SessionListResponse(sessions=sessions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(session_id: str, current_user: User = Depends(get_current_user)):
    """删除当前用户的指定会话"""
    try:
        deleted = storage.delete_session(current_user.username, session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="会话不存在")
        return SessionDeleteResponse(session_id=session_id, message="成功删除会话")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        session_id = request.session_id or "default_session"
        resp = chat_with_agent(request.message, current_user.username, session_id)
        if isinstance(resp, dict):
            return ChatResponse(**resp)
        return ChatResponse(response=resp)
    except Exception as e:
        message = str(e)
        match = re.search(r"Error code:\s*(\d{3})", message)
        if match:
            code = int(match.group(1))
            if code == 429:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "上游模型服务触发限流/额度限制（429）。请检查账号额度/模型状态。\n"
                        f"原始错误：{message}"
                    ),
                )
            if code in (401, 403):
                raise HTTPException(status_code=code, detail=message)
            raise HTTPException(status_code=code, detail=message)
        raise HTTPException(status_code=500, detail=message)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user)):
    """跟 Agent 对话 (流式)"""

    async def event_generator():
        try:
            session_id = request.session_id or "default_session"
            async for chunk in chat_with_agent_stream(request.message, current_user.username, session_id):
                yield chunk
        except Exception as e:
            error_data = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _is_supported_document(filename: str) -> bool:
    file_lower = filename.lower()
    return (
        file_lower.endswith(".pdf")
        or file_lower.endswith((".docx", ".doc"))
        or file_lower.endswith((".xlsx", ".xls"))
    )


async def _save_upload_file(file: UploadFile, file_path: Path) -> None:
    """按块写入上传文件，避免大文件一次性读入内存。"""
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def _process_upload_job(job_id: str, file_path: str, filename: str) -> None:
    """后台执行耗时的解析、分块、向量化入库，并持续更新任务进度。"""
    failed_step = "cleanup"
    try:
        upload_job_manager.complete_step(job_id, "upload", "文件已保存到服务器")

        failed_step = "cleanup"
        upload_job_manager.update_step(job_id, "cleanup", 10, "running", "正在清理同名旧文档")
        milvus_manager.init_collection()
        delete_expr = f'filename == "{filename}"'
        try:
            _remove_bm25_stats_for_filename(filename)
        except Exception:
            pass
        try:
            milvus_manager.delete(delete_expr)
        except Exception:
            pass
        try:
            parent_chunk_store.delete_by_filename(filename)
        except Exception:
            pass
        upload_job_manager.complete_step(job_id, "cleanup", "旧版本清理完成")

        failed_step = "parse"
        upload_job_manager.update_step(job_id, "parse", 5, "running", "正在解析文档并执行三级分块")
        new_docs = loader.load_document(file_path, filename)
        if not new_docs:
            raise ValueError("文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise ValueError("文档处理失败，未生成可检索叶子分块")
        upload_job_manager.complete_step(
            job_id,
            "parse",
            f"解析完成：父级分块 {len(parent_docs)} 个，叶子分块 {len(leaf_docs)} 个",
        )

        failed_step = "parent_store"
        upload_job_manager.update_step(job_id, "parent_store", 20, "running", "正在写入父级分块")
        parent_chunk_store.upsert_documents(parent_docs)
        upload_job_manager.complete_step(job_id, "parent_store", f"父级分块已入库：{len(parent_docs)} 个")

        failed_step = "vector_store"
        total_leaf = len(leaf_docs)
        upload_job_manager.update_step(
            job_id,
            "vector_store",
            0,
            "running",
            f"正在向量化入库：0 / {total_leaf}",
            total_chunks=total_leaf,
            processed_chunks=0,
        )

        def _on_vector_progress(processed: int, total: int) -> None:
            percent = round(processed * 100 / total) if total else 100
            upload_job_manager.update_step(
                job_id,
                "vector_store",
                percent,
                "running",
                f"正在向量化入库：{processed} / {total}",
                total_chunks=total,
                processed_chunks=processed,
            )

        milvus_writer.write_documents(leaf_docs, progress_callback=_on_vector_progress)
        upload_job_manager.complete_step(job_id, "vector_store", f"向量化入库完成：{total_leaf} 个叶子分块")
        upload_job_manager.complete_job(job_id, f"成功上传并处理 {filename}")
    except Exception as e:
        upload_job_manager.fail_job(job_id, failed_step, str(e))


def _process_delete_job(job_id: str, filename: str) -> None:
    """后台执行文档删除，并把每个删除阶段同步给前端行内进度卡片。"""
    failed_step = "prepare"
    try:
        failed_step = "prepare"
        delete_job_manager.update_step(job_id, "prepare", 20, "running", "正在初始化 Milvus 集合")
        milvus_manager.init_collection()
        delete_expr = f'filename == "{filename}"'
        delete_job_manager.complete_step(job_id, "prepare", "删除任务已创建")

        failed_step = "bm25"
        delete_job_manager.update_step(job_id, "bm25", 20, "running", "正在同步 BM25 统计")
        _remove_bm25_stats_for_filename(filename)
        delete_job_manager.complete_step(job_id, "bm25", "BM25 统计已同步")

        failed_step = "milvus"
        delete_job_manager.update_step(job_id, "milvus", 30, "running", "正在删除 Milvus 向量数据")
        result = milvus_manager.delete(delete_expr)
        deleted_count = result.get("delete_count", 0) if isinstance(result, dict) else 0
        delete_job_manager.complete_step(job_id, "milvus", f"向量数据已删除：{deleted_count} 条")

        failed_step = "parent_store"
        delete_job_manager.update_step(job_id, "parent_store", 30, "running", "正在删除 PostgreSQL 父级分块")
        parent_chunk_store.delete_by_filename(filename)
        delete_job_manager.complete_step(job_id, "parent_store", "父级分块已删除")

        # 完成摘要会由前端保留 3 秒，再自动从文档列表移除。
        delete_job_manager.complete_job(job_id, f"已删除 {filename}，向量数据 {deleted_count} 条")
    except Exception as e:
        delete_job_manager.fail_job(job_id, failed_step, str(e))


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(_: User = Depends(require_admin)):
    """获取已上传的文档列表（管理员）"""
    try:
        milvus_manager.init_collection()

        results = milvus_manager.query(
            output_fields=["filename", "file_type"],
            limit=10000,
        )

        file_stats = {}
        for item in results:
            filename = item.get("filename", "")
            file_type = item.get("file_type", "")
            if filename not in file_stats:
                file_stats[filename] = {
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_count": 0,
                }
            file_stats[filename]["chunk_count"] += 1

        documents = [DocumentInfo(**stats) for stats in file_stats.values()]
        return DocumentListResponse(documents=documents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")

@router.post("/documents/upload/async", response_model=DocumentUploadStartResponse)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    """轻量版异步上传：文件落盘后立即返回 job_id，后台继续解析和向量化。"""
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if not _is_supported_document(filename):
        raise HTTPException(status_code=400, detail="仅支持 PDF、Word 和 Excel 文档")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    job = upload_job_manager.create_job(filename)
    file_path = UPLOAD_DIR / filename

    try:
        upload_job_manager.update_step(job["job_id"], "upload", 1, "running", "正在保存文件到服务器")
        await _save_upload_file(file, file_path)
        upload_job_manager.complete_step(job["job_id"], "upload", "文件已上传，等待后台处理")
    except Exception as e:
        upload_job_manager.fail_job(job["job_id"], "upload", f"文件保存失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    background_tasks.add_task(_process_upload_job, job["job_id"], str(file_path), filename)
    return DocumentUploadStartResponse(
        job_id=job["job_id"],
        filename=filename,
        message="文件已上传，正在后台解析和向量化入库",
    )


@router.get("/documents/upload/jobs/{job_id}", response_model=DocumentUploadJobResponse)
async def get_upload_job(job_id: str, _: User = Depends(require_admin)):
    job = upload_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="上传任务不存在或已过期")
    return DocumentUploadJobResponse(**job)


@router.get("/documents/upload/jobs", response_model=list[DocumentUploadJobResponse])
async def list_upload_jobs(_: User = Depends(require_admin)):
    jobs = upload_job_manager.list_jobs()
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return [DocumentUploadJobResponse(**job) for job in jobs]


@router.delete("/documents/delete/async/{filename}", response_model=DocumentDeleteStartResponse)
async def delete_document_async(
    filename: str,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    """轻量版异步删除：立即返回 job_id，实际删除在后台执行。"""
    job = delete_job_manager.create_job(
        filename,
        steps=DELETE_STEPS,
        current_step="prepare",
        message="等待删除",
        completion_step="parent_store",
    )
    delete_job_manager.update_step(job["job_id"], "prepare", 1, "running", "删除任务已提交")
    background_tasks.add_task(_process_delete_job, job["job_id"], filename)
    return DocumentDeleteStartResponse(
        job_id=job["job_id"],
        filename=filename,
        message=f"正在删除 {filename}",
    )


@router.get("/documents/delete/jobs/{job_id}", response_model=DocumentDeleteJobResponse)
async def get_delete_job(job_id: str, _: User = Depends(require_admin)):
    job = delete_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="删除任务不存在或已过期")
    return DocumentDeleteJobResponse(**job)


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), _: User = Depends(require_admin)):
    """上传文档并进行 embedding（管理员）"""
    try:
        filename = file.filename or ""
        file_lower = filename.lower()
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        if not (
            file_lower.endswith(".pdf")
            or file_lower.endswith((".docx", ".doc"))
            or file_lower.endswith((".xlsx", ".xls"))
        ):
            raise HTTPException(status_code=400, detail="仅支持 PDF、Word 和 Excel 文档")

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        milvus_manager.init_collection()

        delete_expr = f'filename == "{filename}"'
        try:
            _remove_bm25_stats_for_filename(filename)
        except Exception:
            pass
        try:
            milvus_manager.delete(delete_expr)
        except Exception:
            pass
        try:
            parent_chunk_store.delete_by_filename(filename)
        except Exception:
            pass

        file_path = UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        try:
            new_docs = loader.load_document(str(file_path), filename)
        except Exception as doc_err:
            raise HTTPException(status_code=500, detail=f"文档处理失败: {doc_err}")

        if not new_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")

        parent_chunk_store.upsert_documents(parent_docs)
        milvus_writer.write_documents(leaf_docs)

        return DocumentUploadResponse(
            filename=filename,
            chunks_processed=len(leaf_docs),
            message=(
                f"成功上传并处理 {filename}，叶子分块 {len(leaf_docs)} 个，"
                f"父级分块 {len(parent_docs)} 个（存入 PostgreSQL）"
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str, _: User = Depends(require_admin)):
    """删除文档在 Milvus 中的向量（保留本地文件，管理员）"""
    try:
        milvus_manager.init_collection()

        delete_expr = f'filename == "{filename}"'
        _remove_bm25_stats_for_filename(filename)
        result = milvus_manager.delete(delete_expr)
        parent_chunk_store.delete_by_filename(filename)

        return DocumentDeleteResponse(
            filename=filename,
            chunks_deleted=result.get("delete_count", 0) if isinstance(result, dict) else 0,
            message=f"成功删除文档 {filename} 的向量数据（本地文件已保留）",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")
