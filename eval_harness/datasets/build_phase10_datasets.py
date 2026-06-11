from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

SUPPORT_TICKETS = WORKSPACE_ROOT / "data" / "processed" / "customer_support" / "support_tickets.jsonl"
KG_RELATIONS = WORKSPACE_ROOT / "data" / "processed" / "enterprise_kg" / "relations.jsonl"
KG_NODES = WORKSPACE_ROOT / "data" / "processed" / "enterprise_kg" / "nodes.jsonl"
MULTIDOC_DIAL = WORKSPACE_ROOT / "data" / "raw" / "multidoc2dial" / "multidoc2dial_dial_validation.json"

OUTPUT_DIR = PROJECT_ROOT / "eval_harness" / "datasets"


def _read_jsonl(path: Path, limit: int | None = None):
    count = 0
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if limit is not None and count >= limit:
                break
            if line.strip():
                count += 1
                yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    path.with_suffix(".summary.json").write_text(
        json.dumps({"path": str(path), "case_count": len(rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_customer_support_cases(limit: int) -> list[dict[str, Any]]:
    cases = []
    for idx, ticket in enumerate(_read_jsonl(SUPPORT_TICKETS, limit=limit), 1):
        customer_id = ticket.get("customer_id")
        product = ticket.get("product")
        issue_type = ticket.get("issue_type")
        text = f"Customer {customer_id} reports {issue_type} on {product}. {ticket.get('summary', '')}"
        cases.append(
            {
                "case_id": f"cust_{idx:04d}",
                "dataset": "customer_support_cases",
                "ticket_text": text,
                "customer_id": customer_id,
                "product": product,
                "issue_type": issue_type,
                "expected_tools": ["classify_intent", "detect_sentiment", "assign_priority", "find_related_tickets"],
                "expected_priority": ticket.get("priority"),
                "expected_memory_keys": [customer_id, product, issue_type],
                "metadata": {"ticket_id": ticket.get("ticket_id"), "status": ticket.get("status")},
            }
        )
    return cases


def build_enterprise_kg_cases(limit: int) -> list[dict[str, Any]]:
    node_names = {row["node_id"]: row.get("name", row["node_id"]) for row in _read_jsonl(KG_NODES)}
    cases = []
    for relation in _read_jsonl(KG_RELATIONS):
        if relation.get("type") not in {"CUSTOMER_OPENED_TICKET", "TICKET_MENTIONS_PRODUCT", "DOCUMENT_MENTIONS_SERVICE", "TEAM_OWNS_SERVICE"}:
            continue
        source_id = relation.get("source_id")
        target_id = relation.get("target_id")
        entity = node_names.get(source_id, source_id)
        cases.append(
            {
                "case_id": f"kg_{len(cases)+1:04d}",
                "dataset": "enterprise_kg_cases",
                "query_entity": entity,
                "user_query": f"Find graph relations around {entity}",
                "expected_tools": ["enterprise_kg_query"],
                "expected_relations": [
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "type": relation.get("type"),
                    }
                ],
                "metadata": {"target_name": node_names.get(target_id, target_id)},
            }
        )
        if len(cases) >= limit:
            break
    return cases


def build_multidoc_dialogue_cases(limit: int) -> list[dict[str, Any]]:
    with MULTIDOC_DIAL.open("r", encoding="utf-8") as file:
        data = json.load(file)
    cases = []
    for domain, dialogues in data.get("dial_data", {}).items():
        if isinstance(dialogues, dict):
            iterable = []
            for value in dialogues.values():
                iterable.extend(value)
        else:
            iterable = dialogues
        for dialogue in iterable:
            turns = dialogue.get("turns", [])
            user_turns = [turn for turn in turns if turn.get("role") == "user"]
            agent_turns = [turn for turn in turns if turn.get("role") == "agent"]
            if not user_turns or not agent_turns:
                continue
            refs = []
            for turn in turns:
                for ref in turn.get("references", []) or []:
                    doc_id = ref.get("doc_id")
                    if doc_id and doc_id not in refs:
                        refs.append(doc_id)
            cases.append(
                {
                    "case_id": f"dialogue_{len(cases)+1:04d}",
                    "dataset": "multidoc_dialogue_cases",
                    "domain": domain,
                    "dialogue_id": dialogue.get("dial_id"),
                    "history": turns[:4],
                    "user_query": user_turns[-1].get("utterance"),
                    "reference_answer": agent_turns[-1].get("utterance"),
                    "expected_doc_ids": refs[:5],
                    "expected_tools": ["search_enterprise_kb"],
                    "expected_memory_keys": [turn.get("utterance", "")[:40] for turn in turns[:2]],
                }
            )
            if len(cases) >= limit:
                return cases
    return cases


def build_all(limit: int) -> dict[str, int]:
    outputs = {
        "customer_support_cases": build_customer_support_cases(limit),
        "enterprise_kg_cases": build_enterprise_kg_cases(limit),
        "multidoc_dialogue_cases": build_multidoc_dialogue_cases(limit),
    }
    for name, rows in outputs.items():
        _write_jsonl(OUTPUT_DIR / f"{name}.jsonl", rows)
    return {name: len(rows) for name, rows in outputs.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Phase 10 eval datasets.")
    parser.add_argument("--limit", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(build_all(args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
