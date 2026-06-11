import json
import asyncio
import re
from typing import Any
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, SystemMessage
from project.backend.tools.enterprise_kb_tools import (
    get_last_rag_context,
    reset_tool_call_guards,
    search_enterprise_kb,
    set_rag_step_queue,
)
from project.backend.tools.customer_ops_tools import (
    create_followup_task,
    get_customer_profile,
    search_customer_tickets,
    update_customer_memory,
)
from project.backend.tools.enterprise_kg_tools import (
    enterprise_kg_query,
    find_owner_team,
    find_related_tickets,
    get_customer_graph,
    get_product_dependency_graph,
    trace_issue_impact,
)
from project.backend.knowledge_graph.kg_query_tool import enterprise_kg_query as query_enterprise_kg
from datetime import datetime
from project.backend.db.postgres import SessionLocal
from project.backend.db.models import ChatMessage, ChatSession, User
from project.backend.db.redis_cache import cache
from project.backend.core.config import get_llm_config

LLM_CONFIG = get_llm_config()
API_KEY = LLM_CONFIG.api_key
MODEL = LLM_CONFIG.model
BASE_URL = LLM_CONFIG.base_url
MODEL_PROVIDER = LLM_CONFIG.provider

class ConversationStorage:
    """对话存储（PostgreSQL + Redis）。"""

    @staticmethod
    def _messages_cache_key(user_id: str, session_id: str) -> str:
        return f"chat_messages:{user_id}:{session_id}"

    @staticmethod
    def _sessions_cache_key(user_id: str) -> str:
        return f"chat_sessions:{user_id}"

    @staticmethod
    def _to_langchain_messages(records: list[dict]) -> list:
        messages = []
        for msg_data in records:
            msg_type = msg_data.get("type")
            content = msg_data.get("content", "")
            if msg_type == "human":
                messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                messages.append(AIMessage(content=content))
            elif msg_type == "system":
                messages.append(SystemMessage(content=content))
        return messages

    def save(self, user_id: str, session_id: str, messages: list, metadata: dict = None, extra_message_data: list = None):
        """保存对话"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return

            session = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id, ChatSession.session_id == session_id)
                .first()
            )
            if not session:
                session = ChatSession(user_id=user.id, session_id=session_id, metadata_json=metadata or {})
                db.add(session)
                db.flush()
            else:
                session.metadata_json = metadata or {}

            db.query(ChatMessage).filter(ChatMessage.session_ref_id == session.id).delete(synchronize_session=False)

            serialized = []
            now = datetime.utcnow()
            for idx, msg in enumerate(messages):
                rag_trace = None
                if extra_message_data and idx < len(extra_message_data):
                    extra = extra_message_data[idx] or {}
                    rag_trace = extra.get("rag_trace")

                db.add(
                    ChatMessage(
                        session_ref_id=session.id,
                        message_type=msg.type,
                        content=str(msg.content),
                        timestamp=now,
                        rag_trace=rag_trace,
                    )
                )
                serialized.append(
                    {
                        "type": msg.type,
                        "content": str(msg.content),
                        "timestamp": now.isoformat(),
                        "rag_trace": rag_trace,
                    }
                )

            session.updated_at = now
            db.commit()

            cache.set_json(self._messages_cache_key(user_id, session_id), serialized)
            cache.delete(self._sessions_cache_key(user_id))
        finally:
            db.close()

    def load(self, user_id: str, session_id: str) -> list:
        """加载对话"""
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            return self._to_langchain_messages(cached)

        records = self.get_session_messages(user_id, session_id)
        cache.set_json(self._messages_cache_key(user_id, session_id), records)
        return self._to_langchain_messages(records)

    def list_sessions(self, user_id: str) -> list:
        """列出用户的所有会话"""
        return [item["session_id"] for item in self.list_session_infos(user_id)]

    def list_session_infos(self, user_id: str) -> list[dict]:
        cached = cache.get_json(self._sessions_cache_key(user_id))
        if cached is not None:
            return cached

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return []

            sessions = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id)
                .order_by(ChatSession.updated_at.desc())
                .all()
            )
            result = []
            for s in sessions:
                count = db.query(ChatMessage).filter(ChatMessage.session_ref_id == s.id).count()
                result.append(
                    {
                        "session_id": s.session_id,
                        "updated_at": s.updated_at.isoformat(),
                        "message_count": count,
                    }
                )
            cache.set_json(self._sessions_cache_key(user_id), result)
            return result
        finally:
            db.close()

    def get_session_messages(self, user_id: str, session_id: str) -> list[dict]:
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            return cached

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return []
            session = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id, ChatSession.session_id == session_id)
                .first()
            )
            if not session:
                return []

            rows = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_ref_id == session.id)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            result = [
                {
                    "type": row.message_type,
                    "content": row.content,
                    "timestamp": row.timestamp.isoformat(),
                    "rag_trace": row.rag_trace,
                }
                for row in rows
            ]
            cache.set_json(self._messages_cache_key(user_id, session_id), result)
            return result
        finally:
            db.close()

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """删除指定用户的会话，返回是否删除成功"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return False
            session = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id, ChatSession.session_id == session_id)
                .first()
            )
            if not session:
                return False

            db.delete(session)
            db.commit()
            cache.delete(self._messages_cache_key(user_id, session_id))
            cache.delete(self._sessions_cache_key(user_id))
            return True
        finally:
            db.close()



def create_agent_instance():
    model = init_chat_model(
        model=MODEL,
        model_provider=MODEL_PROVIDER,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0.3,
        stream_usage=True,
    )

    agent = create_agent(
        model=model,
        tools=[
            search_enterprise_kb,
            get_customer_profile,
            search_customer_tickets,
            update_customer_memory,
            create_followup_task,
            enterprise_kg_query,
            get_customer_graph,
            get_product_dependency_graph,
            find_related_tickets,
            find_owner_team,
            trace_issue_impact,
        ],
        system_prompt=(
            "You are an enterprise customer-ops agent for support and operations teams. "
            "Coordinate customer memory, historical tickets, enterprise knowledge-base retrieval, "
            "and enterprise knowledge-graph tools, then produce a practical answer with evidence. "
            "You must finish each user turn with a final answer. "
            "For customer-specific questions, first use get_customer_profile and search_customer_tickets. "
            "For document, runbook, policy, deployment, configuration, or troubleshooting questions, use search_enterprise_kb. "
            "For owner, dependency, impact, related ticket, customer-product, team, service, or graph-path questions, use enterprise KG tools. "
            "For combined customer-history plus product-doc questions, use this order when applicable: "
            "get_customer_profile once, search_customer_tickets once, enterprise_kg_query once, search_enterprise_kb once, then final answer. "
            "If a question mentions both a customer id such as CustXXXX and a service or product such as SSO or perf-canary, "
            "you must call enterprise_kg_query for the customer id or service before writing the final answer. "
            "Do not call any tool more than once in one turn. Do not call another tool after search_enterprise_kb returns useful chunks. "
            "Use update_customer_memory only when the user asks you to remember a durable customer fact. "
            "Use create_followup_task only when a follow-up action should be saved. "
            "Answer in Chinese by default. Structure the final answer as: direct answer, document evidence, customer/history context, "
            "KG relationship or impact, recommended next steps, and uncertainty if any. "
            "Only write document evidence when search_enterprise_kb returns Retrieved Chunks. "
            "If no citations are returned, explicitly say no reliable document citation was found. "
            "Do not claim counts, open ticket totals, or impact scope unless a tool result directly supports it. "
            "Do not expose hidden chain-of-thought. If retrieved evidence is insufficient, say what is missing instead of inventing facts."
        ),
    )
    return agent, model


agent, model = create_agent_instance()

storage = ConversationStorage()


def _try_json(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


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


def _dedupe_items(items: list, key_fn, limit: int) -> list:
    deduped = []
    seen = set()
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _source_items_from_rag_trace(rag_trace: dict | None) -> list[dict]:
    if not rag_trace:
        return []
    chunks = (
        rag_trace.get("retrieved_chunks")
        or rag_trace.get("expanded_retrieved_chunks")
        or rag_trace.get("initial_retrieved_chunks")
        or []
    )
    sources = []
    seen = set()
    for chunk in chunks:
        title = chunk.get("title") or chunk.get("filename") or "Unknown"
        doc_id = chunk.get("doc_id") or chunk.get("chunk_id") or title
        key = (title, doc_id)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "title": title,
                "doc_id": doc_id,
                "source_type": chunk.get("source_type") or chunk.get("file_type") or "knowledge_base",
                "preview": (chunk.get("text") or "")[:260],
                "score": chunk.get("rerank_score") or chunk.get("score"),
            }
        )
    return sources[:6]


def _source_items_from_kb_output(content: str) -> list[dict]:
    if not content.startswith("Retrieved Chunks:"):
        return []

    pattern = re.compile(
        r"\[(?P<rank>\d+)\]\s+(?P<title>.*?)\s+"
        r"\(doc_id=(?P<doc_id>.*?),\s+source_type=(?P<source_type>.*?),\s+Page\s+(?P<page>.*?)\):\n"
        r"(?P<text>.*?)(?=\n\n---\n\n|\Z)",
        re.DOTALL,
    )
    sources = []
    seen = set()
    for match in pattern.finditer(content):
        title = match.group("title").strip() or "Unknown"
        doc_id = match.group("doc_id").strip()
        key = (title, doc_id)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "title": title,
                "doc_id": doc_id,
                "source_type": match.group("source_type").strip() or "knowledge_base",
                "preview": match.group("text").strip()[:260],
                "page": match.group("page").strip(),
            }
        )
    return sources[:6]


def _memory_items_from_payload(payload: dict[str, Any]) -> list[dict]:
    memory_items = []
    profile = payload.get("profile")
    if profile:
        memory_items.append(
            {
                "title": "Customer profile",
                "body": (
                    f"{profile.get('customer_id', '')} · {profile.get('segment', 'customer')} · "
                    f"{', '.join(profile.get('products') or [])}"
                ),
                "meta": "get_customer_profile",
            }
        )
    for ticket in payload.get("tickets", [])[:3]:
        memory_items.append(
            {
                "title": "Related ticket",
                "body": (
                    f"{ticket.get('ticket_id', '')} · {ticket.get('product', '')} / "
                    f"{ticket.get('issue_type', '')} · {ticket.get('priority', '')} · {ticket.get('status', '')}"
                ),
                "meta": "search_customer_tickets",
            }
        )
    return memory_items


def _extract_agent_trace(result_messages: list, rag_trace: dict | None) -> dict:
    tools = []
    paths = []
    memory = []
    sources = _source_items_from_rag_trace(rag_trace)
    tool_outputs = []

    for msg in result_messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                tools.append(name)

        if getattr(msg, "type", None) != "tool":
            continue
        name = getattr(msg, "name", "") or ""
        content = str(getattr(msg, "content", "") or "")
        parsed = _try_json(content)
        tool_outputs.append({"name": name, "content": content[:1200]})
        if name == "search_enterprise_kb" and not sources:
            sources = _source_items_from_kb_output(content)

        if isinstance(parsed, dict):
            if name in {
                "enterprise_kg_query",
                "get_customer_graph",
                "get_product_dependency_graph",
                "find_related_tickets",
                "find_owner_team",
                "trace_issue_impact",
            }:
                paths.extend(_format_graph_paths(parsed))
            if name in {"get_customer_profile", "search_customer_tickets"}:
                memory.extend(_memory_items_from_payload(parsed))

    deduped_tools = []
    seen_tools = set()
    for tool_name in tools:
        if tool_name not in seen_tools:
            seen_tools.add(tool_name)
            deduped_tools.append(tool_name)

    paths = _dedupe_items(paths, lambda item: item, 5)
    memory = _dedupe_items(memory, lambda item: (item.get("title"), item.get("body"), item.get("meta")), 5)
    sources = _dedupe_items(sources, lambda item: (item.get("title"), item.get("doc_id")), 5)

    return {
        "tools": deduped_tools,
        "sources": sources,
        "paths": paths,
        "memory": memory,
        "tool_outputs": tool_outputs,
        "eval": {
            "tool_call_count": len(deduped_tools),
            "citation_coverage": 1.0 if sources else 0.0,
            "kg_paths": len(paths),
            "memory_hits": len(memory),
        },
    }


def _kg_entity_candidates(text: str) -> list[str]:
    candidates = []
    customer = re.search(r"\bCust[A-Z0-9]+\b", text, re.IGNORECASE)
    if customer:
        candidates.append(customer.group(0))
    candidates.extend(re.findall(r"\b[a-z][a-z0-9]+(?:-[a-z0-9]+)+\b", text))
    for token in ("SSO", "API", "GPU", "SLA", "KYC", "Billing", "Exam"):
        if token.lower() in text.lower():
            candidates.append(token)

    deduped = []
    seen = set()
    for item in candidates:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _ensure_kg_trace(user_text: str, agent_trace: dict) -> dict:
    if agent_trace.get("paths"):
        return agent_trace

    for entity in _kg_entity_candidates(user_text)[:3]:
        graph = query_enterprise_kg(entity, depth=2)
        paths = _format_graph_paths(graph)
        if not paths:
            continue
        tools = agent_trace.setdefault("tools", [])
        if "enterprise_kg_query" not in tools:
            tools.append("enterprise_kg_query")
        agent_trace["paths"] = _dedupe_items(paths, lambda item: item, 5)
        agent_trace.setdefault("tool_outputs", []).append(
            {"name": "enterprise_kg_query", "content": json.dumps(graph, ensure_ascii=False)[:1200]}
        )
        eval_items = agent_trace.setdefault("eval", {})
        eval_items["tool_call_count"] = len(tools)
        eval_items["kg_paths"] = len(paths)
        break
    return agent_trace


def _align_answer_with_evidence(response: str, agent_trace: dict) -> str:
    sources = agent_trace.get("sources") or []
    paths = agent_trace.get("paths") or []

    if sources:
        return response
    if "文档证据" in response or "引用" in response or "知识库" in response:
        return (
            response
            + "\n\n证据校验：本次没有获得可展示的 RAG Sources，因此文档相关判断只能作为待验证建议，"
            "不能视为已被知识库原文引用支持。"
        )
    if not paths:
        return (
            response
            + "\n\n证据校验：本次没有获得可展示的 RAG Sources 或 KG Paths，建议补充检索关键词后重试。"
        )
    return response

def summarize_old_messages(model, messages: list) -> str:
    """将旧消息总结为摘要"""
    # 提取旧对话
    old_conversation = "\n".join([
        f"{'用户' if msg.type == 'human' else 'AI'}: {msg.content}"
        for msg in messages
    ])

    # 生成摘要
    summary_prompt = f"""请总结以下对话的关键信息：

{old_conversation}
总结（包含用户信息、重要事实、待办事项）："""

    summary = model.invoke(summary_prompt).content
    return summary


def chat_with_agent(user_text: str, user_id: str = "default_user", session_id: str = "default_session"):
    """使用 Agent 处理用户消息并返回响应"""
    messages = storage.load(user_id, session_id)

    # 清理可能残留的 RAG 上下文，避免跨请求污染
    get_last_rag_context(clear=True)
    reset_tool_call_guards()
    
    if len(messages) > 50:
        summary = summarize_old_messages(model, messages[:40])

        messages = [
            SystemMessage(content=f"之前的对话摘要：\n{summary}")
        ] + messages[40:]

    messages.append(HumanMessage(content=user_text))
    result = agent.invoke(
        {"messages": messages},
        config={"recursion_limit": 20},
    )

    response_content = ""
    if isinstance(result, dict):
        if "output" in result:
            response_content = result["output"]
        elif "messages" in result and result["messages"]:
            msg = result["messages"][-1]
            response_content = getattr(msg, "content", str(msg))
        else:
            response_content = str(result)
    elif hasattr(result, "content"):
        response_content = result.content
    else:
        response_content = str(result)
    
    messages.append(AIMessage(content=response_content))

    result_messages = result.get("messages", []) if isinstance(result, dict) else []
    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None
    agent_trace = _extract_agent_trace(result_messages, rag_trace)
    agent_trace = _ensure_kg_trace(user_text, agent_trace)
    response_content = _align_answer_with_evidence(response_content, agent_trace)

    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra_message_data)

    return {
        "response": response_content,
        "rag_trace": rag_trace,
        **agent_trace,
    }


async def chat_with_agent_stream(user_text: str, user_id: str = "default_user", session_id: str = "default_session"):
    """使用 Agent 处理用户消息并流式返回响应。
    
    架构：使用统一输出队列 + 后台任务，确保 RAG 检索步骤在工具执行期间实时推送，
    而非等待工具完成后才显示。
    """
    messages = storage.load(user_id, session_id)

    # 清理可能残留的 RAG 上下文
    get_last_rag_context(clear=True)
    reset_tool_call_guards()

    # 统一输出队列：所有事件（content / rag_step）都汇入这里
    output_queue = asyncio.Queue()

    class _RagStepProxy:
        """代理对象：将 emit_rag_step 的原始 step dict 包装后放入统一输出队列。"""
        def put_nowait(self, step):
            output_queue.put_nowait({"type": "rag_step", "step": step})

    set_rag_step_queue(_RagStepProxy())

    if len(messages) > 50:
        summary = summarize_old_messages(model, messages[:40])
        messages = [
            SystemMessage(content=f"之前的对话摘要：\n{summary}")
        ] + messages[40:]

    messages.append(HumanMessage(content=user_text))

    full_response = ""

    async def _agent_worker():
        """后台任务：运行 agent 并将内容 chunk 推入输出队列。"""
        nonlocal full_response
        try:
            async for msg, metadata in agent.astream(
                {"messages": messages},
                stream_mode="messages",
                config={"recursion_limit": 20},
            ):
                if not isinstance(msg, AIMessageChunk):
                    continue
                if getattr(msg, "tool_call_chunks", None):
                    continue

                content = ""
                if isinstance(msg.content, str):
                    content = msg.content
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, str):
                            content += block
                        elif isinstance(block, dict) and block.get("type") == "text":
                            content += block.get("text", "")

                if content:
                    full_response += content
                    await output_queue.put({"type": "content", "content": content})
        except Exception as e:
            await output_queue.put({"type": "error", "content": str(e)})
        finally:
            # 哨兵：通知主循环 agent 已完成
            await output_queue.put(None)

    # 启动后台任务
    agent_task = asyncio.create_task(_agent_worker())

    try:
        # 主循环：持续从统一队列取事件并 yield SSE
        # RAG 步骤在工具执行期间通过 call_soon_threadsafe 实时入队，不需要等 agent 产出 chunk
        while True:
            event = await output_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
    except GeneratorExit:
        # 客户端断开连接（AbortController）时，FastAPI 会向此生成器抛出 GeneratorExit
        # 我们必须在此处取消后台任务
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass  # 任务已成功取消
        raise  # 重新抛出 GeneratorExit 以便 FastAPI 正确处理关闭
    finally:
        # 正常结束或异常退出时清理
        set_rag_step_queue(None)
        if not agent_task.done():
             agent_task.cancel()

    # 获取 RAG trace
    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None

    # 发送 trace 信息
    if rag_trace:
        yield f"data: {json.dumps({'type': 'trace', 'rag_trace': rag_trace})}\n\n"

    # 发送结束信号
    yield "data: [DONE]\n\n"

    # 保存对话
    messages.append(AIMessage(content=full_response))
    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra_message_data)
