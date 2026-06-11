"""Prepare customer support conversations, tickets, and profiles.

The raw CSV is large, so the default run processes a small number of complete
conversations for local iteration. Use `--all` for a full export.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = WORKSPACE_ROOT / "data" / "raw" / "customer_support" / "customer_support_data.csv"
DEFAULT_OUTPUT_DIR = WORKSPACE_ROOT / "data" / "processed" / "customer_support"
DEFAULT_MAX_CONVERSATIONS = 2000

HIGH_PRIORITY_KEYWORDS = (
    "urgent",
    "outage",
    "down",
    "cannot login",
    "can't login",
    "production",
    "blocked",
    "critical",
    "expedite",
)
LOW_PRIORITY_KEYWORDS = (
    "how to",
    "question",
    "docs",
    "documentation",
    "where can i",
)


@dataclass
class ProfileAccumulator:
    customer_id: str
    industries: Counter[str] = field(default_factory=Counter)
    products: Counter[str] = field(default_factory=Counter)
    issue_types: Counter[str] = field(default_factory=Counter)
    channels: Counter[str] = field(default_factory=Counter)
    sentiments: Counter[str] = field(default_factory=Counter)
    urgencies: Counter[str] = field(default_factory=Counter)
    intents: Counter[str] = field(default_factory=Counter)
    outcomes: Counter[str] = field(default_factory=Counter)
    conversation_count: int = 0
    high_priority_ticket_count: int = 0
    last_seen_at: str = ""
    ticket_ids: list[str] = field(default_factory=list)

    def add_conversation(self, conversation: dict[str, Any], ticket: dict[str, Any]) -> None:
        self.conversation_count += 1
        for key, counter in (
            ("industry", self.industries),
            ("product", self.products),
            ("issue_type", self.issue_types),
            ("channel", self.channels),
            ("overall_sentiment", self.sentiments),
            ("overall_urgency", self.urgencies),
            ("primary_intent", self.intents),
            ("outcome", self.outcomes),
        ):
            value = str(conversation.get(key) or "").strip()
            if value:
                counter[value] += 1
        if ticket.get("priority") == "high":
            self.high_priority_ticket_count += 1
        if len(self.ticket_ids) < 50:
            self.ticket_ids.append(ticket["ticket_id"])
        timestamp = str(conversation.get("last_message_at") or "")
        if timestamp and timestamp > self.last_seen_at:
            self.last_seen_at = timestamp

    @staticmethod
    def _top(counter: Counter[str], limit: int = 10) -> list[str]:
        return [item for item, _ in counter.most_common(limit)]

    def to_json(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "industries": self._top(self.industries),
            "products": self._top(self.products),
            "common_issue_types": self._top(self.issue_types),
            "channels": self._top(self.channels),
            "sentiments": dict(self.sentiments),
            "urgencies": dict(self.urgencies),
            "primary_intents": self._top(self.intents),
            "outcomes": dict(self.outcomes),
            "conversation_count": self.conversation_count,
            "high_priority_ticket_count": self.high_priority_ticket_count,
            "last_seen_at": self.last_seen_at,
            "sample_ticket_ids": self.ticket_ids,
        }


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _row_to_message(row: dict[str, str]) -> dict[str, str | int]:
    try:
        turn_index = int(_clean(row.get("turn_index")) or 0)
    except ValueError:
        turn_index = 0
    return {
        "turn_index": turn_index,
        "role": _clean(row.get("role")),
        "text": _clean(row.get("text")),
        "timestamp": _clean(row.get("timestamp")),
    }


def _conversation_from_rows(conv_id: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: int(_clean(row.get("turn_index")) or 0))
    first = rows[0]
    messages = [_row_to_message(row) for row in rows if _clean(row.get("text"))]
    timestamps = [_clean(msg.get("timestamp")) for msg in messages if _clean(msg.get("timestamp"))]
    return {
        "conv_id": conv_id,
        "customer_name": _clean(first.get("customer_name")),
        "agent_name": _clean(first.get("agent_name")),
        "industry": _clean(first.get("industry")),
        "product": _clean(first.get("product")),
        "issue_type": _clean(first.get("issue_type")),
        "language": _clean(first.get("language")),
        "channel": _clean(first.get("channel")),
        "overall_sentiment": _clean(first.get("overall_sentiment")),
        "overall_urgency": _clean(first.get("overall_urgency")),
        "outcome": _clean(first.get("outcome")),
        "primary_intent": _clean(first.get("primary_intent")),
        "first_message_at": min(timestamps) if timestamps else "",
        "last_message_at": max(timestamps) if timestamps else "",
        "message_count": len(messages),
        "messages": messages,
    }


def _infer_status(outcome: str) -> str:
    value = outcome.lower()
    if "resolved" in value or "closed" in value or "success" in value:
        return "resolved"
    if "escalat" in value:
        return "escalated"
    if "pending" in value or "open" in value:
        return "open"
    return "simulated_open"


def _infer_priority(conversation: dict[str, Any]) -> str:
    urgency = str(conversation.get("overall_urgency") or "").lower()
    text = " ".join(str(msg.get("text") or "") for msg in conversation.get("messages", [])).lower()
    if urgency == "high" or any(keyword in text for keyword in HIGH_PRIORITY_KEYWORDS):
        return "high"
    if urgency == "low" or any(keyword in text for keyword in LOW_PRIORITY_KEYWORDS):
        return "low"
    return "medium"


def _summarize(conversation: dict[str, Any], max_chars: int = 240) -> str:
    customer_msgs = [
        str(msg.get("text") or "").strip()
        for msg in conversation.get("messages", [])
        if msg.get("role") == "customer" and str(msg.get("text") or "").strip()
    ]
    first_customer_text = customer_msgs[0] if customer_msgs else ""
    prefix = (
        f"{conversation.get('product') or 'Unknown product'} / "
        f"{conversation.get('issue_type') or 'Unknown issue'}"
    )
    summary = f"{prefix}: {first_customer_text}".strip()
    return summary[:max_chars]


def _ticket_from_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    priority = _infer_priority(conversation)
    return {
        "ticket_id": conversation["conv_id"],
        "customer_id": conversation.get("customer_name", ""),
        "product": conversation.get("product", ""),
        "issue_type": conversation.get("issue_type", ""),
        "status": _infer_status(str(conversation.get("outcome") or "")),
        "priority": priority,
        "summary": _summarize(conversation),
        "overall_sentiment": conversation.get("overall_sentiment", ""),
        "overall_urgency": conversation.get("overall_urgency", ""),
        "primary_intent": conversation.get("primary_intent", ""),
        "outcome": conversation.get("outcome", ""),
        "first_message_at": conversation.get("first_message_at", ""),
        "last_message_at": conversation.get("last_message_at", ""),
        "messages": conversation.get("messages", []),
    }


def _iter_conversation_groups(input_path: Path) -> Iterable[tuple[str, list[dict[str, str]]]]:
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        current_id = ""
        rows: list[dict[str, str]] = []
        for row in reader:
            conv_id = _clean(row.get("conv_id"))
            if not conv_id:
                continue
            if current_id and conv_id != current_id:
                yield current_id, rows
                rows = []
            current_id = conv_id
            rows.append(row)
        if current_id and rows:
            yield current_id, rows


def prepare_support_cases(
    input_path: Path,
    output_dir: Path,
    max_conversations: int | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    conversations_path = output_dir / "conversations.jsonl"
    tickets_path = output_dir / "support_tickets.jsonl"
    profiles_path = output_dir / "customer_profiles.jsonl"

    profiles: dict[str, ProfileAccumulator] = {}
    stats = Counter()
    priority_counts = Counter()
    status_counts = Counter()

    with conversations_path.open("w", encoding="utf-8") as conv_out, tickets_path.open("w", encoding="utf-8") as ticket_out:
        for conv_id, rows in _iter_conversation_groups(input_path):
            if max_conversations is not None and stats["conversation_count"] >= max_conversations:
                break
            conversation = _conversation_from_rows(conv_id, rows)
            ticket = _ticket_from_conversation(conversation)
            customer_id = ticket.get("customer_id") or "unknown_customer"
            profiles.setdefault(customer_id, ProfileAccumulator(customer_id=customer_id)).add_conversation(conversation, ticket)

            conv_out.write(json.dumps(conversation, ensure_ascii=False) + "\n")
            ticket_out.write(json.dumps(ticket, ensure_ascii=False) + "\n")

            stats["conversation_count"] += 1
            stats["message_count"] += conversation["message_count"]
            priority_counts[ticket["priority"]] += 1
            status_counts[ticket["status"]] += 1

    with profiles_path.open("w", encoding="utf-8") as profile_out:
        for profile in sorted(profiles.values(), key=lambda item: item.customer_id):
            profile_out.write(json.dumps(profile.to_json(), ensure_ascii=False) + "\n")

    summary = {
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "max_conversations": max_conversations,
        "conversation_count": stats["conversation_count"],
        "message_count": stats["message_count"],
        "customer_profile_count": len(profiles),
        "priority_counts": dict(sorted(priority_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "outputs": {
            "conversations": str(conversations_path),
            "support_tickets": str(tickets_path),
            "customer_profiles": str(profiles_path),
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare customer support data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-conversations", type=int, default=DEFAULT_MAX_CONVERSATIONS)
    parser.add_argument("--all", action="store_true", help="Process all conversations.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    max_conversations = None if args.all else args.max_conversations
    summary = prepare_support_cases(args.input, args.output_dir, max_conversations)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
