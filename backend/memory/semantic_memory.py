from __future__ import annotations

try:
    from project.backend.memory.store import CustomerMemoryStore, default_store
except ModuleNotFoundError:
    from backend.memory.store import CustomerMemoryStore, default_store


class SemanticMemory:
    """Keyword fallback for semantic memory until Milvus-backed recall is wired in."""

    def __init__(self, store: CustomerMemoryStore = default_store) -> None:
        self.store = store

    def search_customer_context(
        self,
        customer_id: str,
        query: str = "",
        limit: int = 5,
    ) -> dict:
        return {
            "profile_memory": self.store.list_memory(
                customer_id,
                memory_type="profile_memory",
                limit=limit,
            ),
            "domain_memory": self.store.get_domain_memory(query=query, limit=limit),
            "tickets": self.store.search_customer_tickets(
                customer_id,
                query=query,
                limit=limit,
            ),
        }
