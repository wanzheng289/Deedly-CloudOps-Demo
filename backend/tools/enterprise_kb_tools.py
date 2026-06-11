from typing import Optional
import json
import re
from pathlib import Path
import requests
from project.backend.core.config import get_weather_config
try:
    from langchain_core.tools import tool
except ImportError:
    from langchain_core.tools import tool

WEATHER_CONFIG = get_weather_config()
AMAP_WEATHER_API = WEATHER_CONFIG.amap_weather_api
AMAP_API_KEY = WEATHER_CONFIG.amap_api_key

_LAST_RAG_CONTEXT = None
_KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0
_RAG_STEP_QUEUE = None  # asyncio.Queue, set by agent before streaming
_RAG_STEP_LOOP = None   # asyncio loop, captured when setting queue
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
ENTERPRISE_DOCS_PATH = WORKSPACE_ROOT / "data" / "processed" / "enterprise_rag_bench" / "sample_documents.jsonl"


def _set_last_rag_context(context: dict):
    global _LAST_RAG_CONTEXT
    _LAST_RAG_CONTEXT = context


def get_last_rag_context(clear: bool = True) -> Optional[dict]:
    """获取最近一次 RAG 检索上下文，默认读取后清空。"""
    global _LAST_RAG_CONTEXT
    context = _LAST_RAG_CONTEXT
    if clear:
        _LAST_RAG_CONTEXT = None
    return context


def reset_tool_call_guards():
    """每轮对话开始时重置工具调用计数。"""
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0


def set_rag_step_queue(queue):
    """设置 RAG 步骤队列，并捕获当前事件循环以便跨线程调度。"""
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    _RAG_STEP_QUEUE = queue
    if queue:
        import asyncio
        try:
            _RAG_STEP_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            _RAG_STEP_LOOP = asyncio.get_event_loop()
    else:
        _RAG_STEP_LOOP = None


def emit_rag_step(icon: str, label: str, detail: str = ""):
    """向队列发送一个 RAG 检索步骤。支持跨线程安全调用。"""
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    if _RAG_STEP_QUEUE is not None and _RAG_STEP_LOOP is not None:
        step = {"icon": icon, "label": label, "detail": detail}
        try:
            if not _RAG_STEP_LOOP.is_closed():
                _RAG_STEP_LOOP.call_soon_threadsafe(_RAG_STEP_QUEUE.put_nowait, step)
        except Exception:
            pass


def _extract_doc_id(query: str) -> str | None:
    match = re.search(r"(?:doc_id\s*=\s*)?(dsid_[A-Za-z0-9]+)", query or "")
    return match.group(1) if match else None


def _chunks_for_doc_id(doc_id: str, max_chunks: int = 5, chunk_size: int = 900) -> list[dict]:
    if not doc_id or not ENTERPRISE_DOCS_PATH.exists():
        return []

    with ENTERPRISE_DOCS_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("doc_id") != doc_id:
                continue

            title = record.get("title") or doc_id
            source_type = record.get("source_type") or "unknown"
            content = record.get("content") or ""
            chunks = []
            for idx in range(max_chunks):
                start = idx * chunk_size
                text = content[start : start + chunk_size].strip()
                if not text:
                    break
                chunks.append(
                    {
                        "id": f"{doc_id}::exact::{idx}",
                        "text": f"# {title}\n\n{text}" if idx == 0 else text,
                        "filename": ENTERPRISE_DOCS_PATH.name,
                        "file_type": "EnterpriseRAGBench",
                        "doc_id": doc_id,
                        "source_type": source_type,
                        "title": title,
                        "page_number": idx + 1,
                        "chunk_id": f"{doc_id}::exact::{idx}",
                        "parent_chunk_id": f"{doc_id}::exact",
                        "root_chunk_id": doc_id,
                        "chunk_level": 1,
                        "chunk_idx": idx,
                        "score": 1.0,
                        "rrf_rank": idx + 1,
                        "rerank_score": 1.0,
                    }
                )
            return chunks
    return []


def get_current_weather(location: str, extensions: Optional[str] = "base") -> str:
    """获取天气信息"""
    if not location:
        return "location参数不能为空"
    if extensions not in ("base", "all"):
        return "extensions参数错误，请输入base或all"

    if not AMAP_WEATHER_API or not AMAP_API_KEY:
        return "天气服务未配置（缺少 AMAP_WEATHER_API 或 AMAP_API_KEY）"

    params = {
        "key": AMAP_API_KEY,
        "city": location,
        "extensions": extensions,
        "output": "json",
    }

    try:
        resp = requests.get(AMAP_WEATHER_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            return f"查询失败：{data.get('info', '未知错误')}"

        if extensions == "base":
            lives = data.get("lives", [])
            if not lives:
                return f"未查询到 {location} 的天气数据"
            w = lives[0]
            return (
                f"【{w.get('city', location)} 实时天气】\n"
                f"天气状况：{w.get('weather', '未知')}\n"
                f"温度：{w.get('temperature', '未知')}℃\n"
                f"湿度：{w.get('humidity', '未知')}%\n"
                f"风向：{w.get('winddirection', '未知')}\n"
                f"风力：{w.get('windpower', '未知')}级\n"
                f"更新时间：{w.get('reporttime', '未知')}"
            )

        forecasts = data.get("forecasts", [])
        if not forecasts:
            return f"未查询到 {location} 的天气预报数据"
        f0 = forecasts[0]
        out = [f"【{f0.get('city', location)} 天气预报】", f"更新时间：{f0.get('reporttime', '未知')}", ""]
        today = (f0.get("casts") or [])[0] if f0.get("casts") else {}
        out += [
            "今日天气：",
            f"  白天：{today.get('dayweather','未知')}",
            f"  夜间：{today.get('nightweather','未知')}",
            f"  气温：{today.get('nighttemp','未知')}~{today.get('daytemp','未知')}℃",
        ]
        return "\n".join(out)

    except requests.exceptions.Timeout:
        return "错误：请求天气服务超时"
    except requests.exceptions.RequestException as e:
        return f"错误：天气服务请求失败 - {e}"
    except Exception as e:
        return f"错误：解析天气数据失败 - {e}"


def _search_enterprise_kb_impl(query: str, tool_name: str = "search_enterprise_kb") -> str:
    """Search for information in the enterprise knowledge base."""
    # ... guards omitted ...
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    if _KNOWLEDGE_TOOL_CALLS_THIS_TURN >= 1:
        return (
            f"TOOL_CALL_LIMIT_REACHED: {tool_name} has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN += 1

    from project.backend.rag.retriever import retrieve_documents
    from project.backend.workflows.enterprise_rag_workflow import run_rag_graph

    # 在同步工具中获取当前的 Loop 可能不可靠，但我们之前是通过 call_soon_threadsafe 调度的。
    # 这里 _RAG_STEP_QUEUE 是在主线程/Loop 设置的全局变量。
    # 如果工具运行在线程池中，它是可以访问到全局变量 _RAG_STEP_QUEUE 的。
    # emit_rag_step 内部做了 try-except 和 get_event_loop()。

    # 问题可能出在 asyncio.get_event_loop() 在子线程中调用会报错或者拿不到主线程的loop。
    # 我们应该在 set_rag_step_queue 时也保存 loop 引用，或者在 emit_rag_step 中更健壮地获取 loop。

    doc_id = _extract_doc_id(query)
    docs = _chunks_for_doc_id(doc_id) if doc_id else []
    if docs:
        rag_trace = {
            "tool_used": True,
            "tool_name": tool_name,
            "query": query,
            "retrieval_mode": "exact_doc_id",
            "rerank_enabled": False,
            "rerank_applied": False,
            "rerank_error": None,
            "retrieved_chunks": docs,
        }
    else:
        fallback = retrieve_documents(query, top_k=5)
        docs = fallback.get("docs", [])
        rag_trace = {
            "tool_used": True,
            "tool_name": tool_name,
            "query": query,
            "retrieval_mode": fallback.get("meta", {}).get("retrieval_mode", "direct"),
            "rerank_enabled": fallback.get("meta", {}).get("rerank_enabled"),
            "rerank_applied": fallback.get("meta", {}).get("rerank_applied"),
            "rerank_error": fallback.get("meta", {}).get("rerank_error"),
            "retrieved_chunks": docs,
        }

    if not docs:
        try:
            rag_result = run_rag_graph(query)
            docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
            rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else rag_trace
        except Exception as exc:
            rag_trace["retrieval_stage"] = "rag_graph_failed"
            rag_trace["rerank_error"] = str(exc)
    if rag_trace:
        _set_last_rag_context({"rag_trace": rag_trace})

    if not docs:
        return "No relevant documents found in the knowledge base."

    formatted = []
    for i, result in enumerate(docs, 1):
        source = result.get("title") or result.get("filename", "Unknown")
        doc_id = result.get("doc_id") or "N/A"
        source_type = result.get("source_type") or "unknown"
        page = result.get("page_number", "N/A")
        text = result.get("text", "")
        formatted.append(f"[{i}] {source} (doc_id={doc_id}, source_type={source_type}, Page {page}):\n{text}")

    return "Retrieved Chunks:\n" + "\n\n---\n\n".join(formatted)


@tool("search_enterprise_kb")
def search_enterprise_kb(query: str) -> str:
    """Search the enterprise knowledge base using hybrid retrieval and return cited chunks."""
    return _search_enterprise_kb_impl(query, tool_name="search_enterprise_kb")


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """Backward-compatible alias for search_enterprise_kb."""
    return _search_enterprise_kb_impl(query, tool_name="search_knowledge_base")
