from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp_servers.common import ToolRegistry, WORKSPACE_ROOT, read_jsonl, write_jsonl


registry = ToolRegistry("memory_mcp")
MEMORY_PATH = WORKSPACE_ROOT / "data" / "processed" / "customer_support" / "memory_items.jsonl"


@registry.tool(description="Read memory items for a customer.")
def read_memory(customer_id: str, memory_type: str | None = None, limit: int = 20) -> dict[str, Any]:
    items = []
    for item in read_jsonl(MEMORY_PATH):
        if item.get("customer_id") != customer_id:
            continue
        if memory_type and item.get("memory_type") != memory_type:
            continue
        items.append(item)
    items.sort(key=lambda row: (row.get("importance", 0), row.get("created_at", "")), reverse=True)
    return {"customer_id": customer_id, "count": len(items[:limit]), "memory": items[:limit]}


@registry.tool(description="Write a memory item for a customer.")
def write_memory(customer_id: str, content: str, memory_type: str = "profile_memory", importance: int = 2, source: str = "mcp") -> dict[str, Any]:
    item = {
        "customer_id": customer_id,
        "memory_type": memory_type,
        "content": content,
        "source": source,
        "importance": importance,
        "tags": [],
        "metadata": {},
        "created_at": datetime.utcnow().isoformat(),
    }
    rows = read_jsonl(MEMORY_PATH)
    rows.append(item)
    write_jsonl(MEMORY_PATH, rows)
    return {"ok": True, "memory": item}


@registry.tool(description="Search memory content by keyword.")
def search_memory(query: str, customer_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    terms = [term.lower() for term in query.split() if term.strip()]
    matches = []
    for item in read_jsonl(MEMORY_PATH):
        if customer_id and item.get("customer_id") != customer_id:
            continue
        content = (item.get("content") or "").lower()
        score = sum(1 for term in terms if term in content) if terms else 1
        if score > 0:
            matches.append((score, item))
    matches.sort(key=lambda row: (row[0], row[1].get("importance", 0)), reverse=True)
    return {"query": query, "count": len(matches[:limit]), "memory": [item for _, item in matches[:limit]]}


@registry.tool(description="Delete memory items matching customer_id and optional content substring.")
def delete_memory(customer_id: str, content_contains: str | None = None) -> dict[str, Any]:
    rows = read_jsonl(MEMORY_PATH)
    kept = []
    deleted = 0
    needle = (content_contains or "").lower()
    for item in rows:
        should_delete = item.get("customer_id") == customer_id and (not needle or needle in (item.get("content") or "").lower())
        if should_delete:
            deleted += 1
        else:
            kept.append(item)
    write_jsonl(MEMORY_PATH, kept)
    return {"ok": True, "deleted_count": deleted}


if __name__ == "__main__":
    registry.cli()
