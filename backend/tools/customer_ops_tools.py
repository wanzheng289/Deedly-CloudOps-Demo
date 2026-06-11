from __future__ import annotations

import json
from typing import Any

try:
    from langchain_core.tools import tool
except Exception:  # pragma: no cover - local validation may not install LangChain
    def tool(name: str):  # type: ignore
        def decorator(func):
            func.name = name
            return func

        return decorator

try:
    from project.backend.memory.profile_memory import ProfileMemory
    from project.backend.memory.semantic_memory import SemanticMemory
    from project.backend.memory.store import MemoryRecord, default_store
except ModuleNotFoundError:
    from backend.memory.profile_memory import ProfileMemory
    from backend.memory.semantic_memory import SemanticMemory
    from backend.memory.store import MemoryRecord, default_store


profile_memory = ProfileMemory(default_store)
semantic_memory = SemanticMemory(default_store)


def _json_result(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_memory_item(memory_item: str | dict) -> dict:
    if isinstance(memory_item, dict):
        return memory_item
    try:
        parsed = json.loads(memory_item)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"content": str(memory_item)}


def _get_customer_profile_impl(customer_id: str) -> str:
    """Return customer profile plus high-value profile memories."""
    profile = profile_memory.get_profile(customer_id)
    if not profile:
        return _json_result(
            {
                "customer_id": customer_id,
                "found": False,
                "message": "Customer profile not found in processed support data.",
            }
        )
    return _json_result({"found": True, "profile": profile})


def _search_customer_tickets_impl(customer_id: str, query: str = "", limit: int = 5) -> str:
    """Search historical support tickets for a customer."""
    tickets = default_store.search_customer_tickets(customer_id=customer_id, query=query, limit=limit)
    return _json_result(
        {
            "customer_id": customer_id,
            "query": query,
            "ticket_count": len(tickets),
            "tickets": tickets,
        }
    )


def _update_customer_memory_impl(customer_id: str, memory_item: str | dict) -> str:
    """Append a long-term profile memory item for a customer."""
    payload = _normalize_memory_item(memory_item)
    content = str(payload.get("content") or payload.get("summary") or "").strip()
    if not content:
        return _json_result({"ok": False, "error": "memory_item.content is required"})

    record = MemoryRecord(
        customer_id=customer_id,
        memory_type=str(payload.get("memory_type") or "profile_memory"),
        content=content,
        source=str(payload.get("source") or "agent"),
        importance=int(payload.get("importance") or 2),
        tags=list(payload.get("tags") or []),
        metadata=dict(payload.get("metadata") or {}),
    )
    saved = default_store.add_memory(record)
    return _json_result({"ok": True, "memory": saved})


def _create_followup_task_impl(customer_id: str, summary: str) -> str:
    """Create a follow-up task as a high-importance memory item."""
    if not summary.strip():
        return _json_result({"ok": False, "error": "summary is required"})
    saved = default_store.add_memory(
        MemoryRecord(
            customer_id=customer_id,
            memory_type="session_memory",
            content=f"Follow-up task: {summary.strip()}",
            source="followup_task",
            importance=3,
            tags=["followup", "task"],
        )
    )
    return _json_result({"ok": True, "task": saved})


@tool("get_customer_profile")
def get_customer_profile(customer_id: str) -> str:
    """Get a customer profile and remembered profile facts by customer_id."""
    return _get_customer_profile_impl(customer_id)


@tool("search_customer_tickets")
def search_customer_tickets(customer_id: str, query: str = "", limit: int = 5) -> str:
    """Search historical support tickets for a customer."""
    return _search_customer_tickets_impl(customer_id=customer_id, query=query, limit=limit)


@tool("update_customer_memory")
def update_customer_memory(customer_id: str, memory_item: str) -> str:
    """Save a long-term memory item for a customer."""
    return _update_customer_memory_impl(customer_id=customer_id, memory_item=memory_item)


@tool("create_followup_task")
def create_followup_task(customer_id: str, summary: str) -> str:
    """Create a follow-up task memory item for a customer."""
    return _create_followup_task_impl(customer_id=customer_id, summary=summary)


def build_customer_context(customer_id: str, query: str = "", ticket_limit: int = 5) -> dict:
    """Convenience helper for workflows that need one customer context object."""
    return {
        "profile": profile_memory.get_profile(customer_id),
        "semantic_memory": semantic_memory.search_customer_context(
            customer_id=customer_id,
            query=query,
            limit=ticket_limit,
        ),
    }
