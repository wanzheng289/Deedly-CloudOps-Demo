from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_SUPPORT_DIR = WORKSPACE_ROOT / "data" / "processed" / "customer_support"
DEFAULT_MEMORY_PATH = WORKSPACE_ROOT / "data" / "processed" / "customer_support" / "memory_items.jsonl"


@dataclass
class MemoryRecord:
    customer_id: str
    memory_type: str
    content: str
    source: str = "manual"
    importance: int = 1
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "source": self.source,
            "importance": self.importance,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                yield json.loads(line)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


class CustomerMemoryStore:
    """Offline memory store backed by Phase 4 JSONL outputs.

    The interface mirrors the future PostgreSQL/Redis/Milvus split while staying
    runnable without infrastructure during resume/project iteration.
    """

    def __init__(
        self,
        support_dir: Path | str = DEFAULT_SUPPORT_DIR,
        memory_path: Path | str = DEFAULT_MEMORY_PATH,
    ) -> None:
        self.support_dir = Path(support_dir)
        self.memory_path = Path(memory_path)

    @property
    def profile_path(self) -> Path:
        return self.support_dir / "customer_profiles.jsonl"

    @property
    def tickets_path(self) -> Path:
        return self.support_dir / "support_tickets.jsonl"

    def get_customer_profile(self, customer_id: str) -> dict[str, Any] | None:
        for profile in _read_jsonl(self.profile_path):
            if profile.get("customer_id") == customer_id:
                profile = dict(profile)
                profile["profile_memory"] = self.list_memory(customer_id, memory_type="profile_memory")
                return profile
        return None

    def search_customer_tickets(
        self,
        customer_id: str,
        query: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        query_terms = {term.lower() for term in _normalize_text(query).split() if term}
        matches: list[tuple[int, dict[str, Any]]] = []
        for ticket in _read_jsonl(self.tickets_path):
            if ticket.get("customer_id") != customer_id:
                continue
            text = " ".join(
                [
                    ticket.get("product", ""),
                    ticket.get("issue_type", ""),
                    ticket.get("summary", ""),
                    ticket.get("primary_intent", ""),
                    ticket.get("outcome", ""),
                ]
            ).lower()
            score = 0
            if not query_terms:
                score = 1
            else:
                score = sum(1 for term in query_terms if term in text)
            if ticket.get("priority") == "high":
                score += 2
            if ticket.get("status") in {"open", "escalated"}:
                score += 1
            if score > 0:
                slim_ticket = dict(ticket)
                slim_ticket["messages"] = slim_ticket.get("messages", [])[:4]
                matches.append((score, slim_ticket))

        matches.sort(
            key=lambda item: (
                item[0],
                item[1].get("last_message_at", ""),
                item[1].get("ticket_id", ""),
            ),
            reverse=True,
        )
        return [ticket for _, ticket in matches[:limit]]

    def add_memory(self, record: MemoryRecord) -> dict[str, Any]:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        payload = record.to_dict()
        with self.memory_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def list_memory(
        self,
        customer_id: str,
        memory_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in _read_jsonl(self.memory_path):
            if item.get("customer_id") != customer_id:
                continue
            if memory_type and item.get("memory_type") != memory_type:
                continue
            records.append(item)
        records.sort(
            key=lambda item: (item.get("importance", 0), item.get("created_at", "")),
            reverse=True,
        )
        return records[:limit]

    def get_domain_memory(self, query: str = "", limit: int = 5) -> list[dict[str, Any]]:
        query_terms = {term.lower() for term in _normalize_text(query).split() if term}
        records: list[tuple[int, dict[str, Any]]] = []
        for item in _read_jsonl(self.memory_path):
            if item.get("memory_type") != "domain_memory":
                continue
            content = _normalize_text(item.get("content", "")).lower()
            tags = " ".join(item.get("tags") or []).lower()
            score = item.get("importance", 1)
            if query_terms:
                score += sum(1 for term in query_terms if term in content or term in tags)
            records.append((score, item))
        records.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
        return [item for _, item in records[:limit]]


default_store = CustomerMemoryStore()
