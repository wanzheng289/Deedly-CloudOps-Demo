"""Build Enterprise KG nodes from processed enterprise/customer datasets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project.backend.knowledge_graph.entity_extractor import extract_enterprise_entities
from project.backend.knowledge_graph.graph_builder import dedupe_nodes, save_nodes


DEFAULT_DOCS = WORKSPACE_ROOT / "data" / "processed" / "enterprise_rag_bench" / "sample_documents.jsonl"
DEFAULT_TICKETS = WORKSPACE_ROOT / "data" / "processed" / "customer_support" / "support_tickets.jsonl"
DEFAULT_OUTPUT = WORKSPACE_ROOT / "data" / "processed" / "enterprise_kg" / "nodes.jsonl"


def _read_jsonl(path: Path, limit: int | None = None):
    count = 0
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if limit is not None and count >= limit:
                break
            line = line.strip()
            if not line:
                continue
            count += 1
            yield json.loads(line)


def build_nodes(docs_path: Path, tickets_path: Path, output_path: Path, doc_limit: int | None, ticket_limit: int | None) -> dict:
    nodes = []
    source_counts = {"documents": 0, "tickets": 0}

    if docs_path.exists():
        for record in _read_jsonl(docs_path, doc_limit):
            nodes.extend(extract_enterprise_entities(record))
            source_counts["documents"] += 1
    if tickets_path.exists():
        for record in _read_jsonl(tickets_path, ticket_limit):
            nodes.extend(extract_enterprise_entities(record))
            source_counts["tickets"] += 1

    deduped = dedupe_nodes(nodes)
    written = save_nodes(output_path, deduped)
    summary = {
        "output_path": str(output_path),
        "source_counts": source_counts,
        "node_count": written,
        "node_type_counts": {},
    }
    for node in deduped:
        summary["node_type_counts"][node.type.value] = summary["node_type_counts"].get(node.type.value, 0) + 1
    output_path.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Enterprise KG nodes.")
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--tickets", type=Path, default=DEFAULT_TICKETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--doc-limit", type=int, default=400)
    parser.add_argument("--ticket-limit", type=int, default=2000)
    parser.add_argument("--all", action="store_true", help="Process all available documents and tickets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_nodes(
        docs_path=args.docs,
        tickets_path=args.tickets,
        output_path=args.output,
        doc_limit=None if args.all else args.doc_limit,
        ticket_limit=None if args.all else args.ticket_limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
