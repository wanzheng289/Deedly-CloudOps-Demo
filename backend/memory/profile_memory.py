from __future__ import annotations

try:
    from project.backend.memory.store import MemoryRecord, CustomerMemoryStore, default_store
except ModuleNotFoundError:
    from backend.memory.store import MemoryRecord, CustomerMemoryStore, default_store


class ProfileMemory:
    """Customer profile memory backed by support profiles and manual facts."""

    def __init__(self, store: CustomerMemoryStore = default_store) -> None:
        self.store = store

    def get_profile(self, customer_id: str) -> dict | None:
        return self.store.get_customer_profile(customer_id)

    def remember(
        self,
        customer_id: str,
        content: str,
        *,
        source: str = "agent",
        importance: int = 2,
        tags: list[str] | None = None,
    ) -> dict:
        return self.store.add_memory(
            MemoryRecord(
                customer_id=customer_id,
                memory_type="profile_memory",
                content=content,
                source=source,
                importance=importance,
                tags=tags or [],
            )
        )

    def list_facts(self, customer_id: str, limit: int = 20) -> list[dict]:
        return self.store.list_memory(customer_id, memory_type="profile_memory", limit=limit)
