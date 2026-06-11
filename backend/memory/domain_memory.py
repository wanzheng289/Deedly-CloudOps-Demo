from __future__ import annotations

try:
    from project.backend.memory.store import MemoryRecord, CustomerMemoryStore, default_store
except ModuleNotFoundError:
    from backend.memory.store import MemoryRecord, CustomerMemoryStore, default_store


class DomainMemory:
    """Reusable operating knowledge such as escalation rules and product caveats."""

    def __init__(self, store: CustomerMemoryStore = default_store) -> None:
        self.store = store

    def remember(
        self,
        content: str,
        *,
        customer_id: str = "GLOBAL",
        source: str = "agent",
        importance: int = 2,
        tags: list[str] | None = None,
    ) -> dict:
        return self.store.add_memory(
            MemoryRecord(
                customer_id=customer_id,
                memory_type="domain_memory",
                content=content,
                source=source,
                importance=importance,
                tags=tags or [],
            )
        )

    def search(self, query: str = "", limit: int = 5) -> list[dict]:
        return self.store.get_domain_memory(query=query, limit=limit)
