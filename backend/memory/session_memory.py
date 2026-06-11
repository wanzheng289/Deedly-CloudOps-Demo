from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionMemory:
    """Short-lived memory for the current support conversation."""

    session_id: str
    max_items: int = 20
    items: list[dict] = field(default_factory=list)

    def add_turn(self, role: str, content: str, metadata: dict | None = None) -> None:
        self.items.append(
            {
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        )
        if len(self.items) > self.max_items:
            self.items = self.items[-self.max_items :]

    def summarize(self) -> dict:
        return {
            "session_id": self.session_id,
            "turn_count": len(self.items),
            "recent_turns": self.items[-6:],
        }
