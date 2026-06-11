import json
from pathlib import Path

from backend.memory.store import CustomerMemoryStore, MemoryRecord


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def test_customer_memory_store_reads_profiles_tickets_and_memory(tmp_path):
    support_dir = tmp_path / "support"
    memory_path = tmp_path / "memory_items.jsonl"
    _write_jsonl(
        support_dir / "customer_profiles.jsonl",
        [
            {
                "customer_id": "Cust001",
                "products": ["SSO"],
                "conversation_count": 1,
            }
        ],
    )
    _write_jsonl(
        support_dir / "support_tickets.jsonl",
        [
            {
                "ticket_id": "T1",
                "customer_id": "Cust001",
                "product": "SSO",
                "issue_type": "Login",
                "priority": "high",
                "status": "open",
                "summary": "Customer cannot login to SSO.",
                "messages": [{"role": "customer", "text": "cannot login"}],
            }
        ],
    )

    store = CustomerMemoryStore(support_dir=support_dir, memory_path=memory_path)
    saved = store.add_memory(
        MemoryRecord(
            customer_id="Cust001",
            memory_type="profile_memory",
            content="Prefers email updates.",
            importance=3,
        )
    )

    profile = store.get_customer_profile("Cust001")
    tickets = store.search_customer_tickets("Cust001", "SSO login")

    assert saved["content"] == "Prefers email updates."
    assert profile["profile_memory"][0]["content"] == "Prefers email updates."
    assert tickets[0]["ticket_id"] == "T1"
