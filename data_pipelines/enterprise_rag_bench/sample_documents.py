"""Sample EnterpriseRAG-Bench documents for the first RAG MVP.

The raw corpus is large, so Phase 2 starts with a small, source-balanced JSONL
file that can be indexed quickly during local development.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = WORKSPACE_ROOT / "data" / "raw" / "enterprise_rag_bench" / "documents.jsonl"
DEFAULT_OUTPUT = WORKSPACE_ROOT / "data" / "processed" / "enterprise_rag_bench" / "sample_documents.jsonl"


def _normalize_document(raw: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(raw.get("doc_id") or "").strip()
    source_type = str(raw.get("source_type") or "unknown").strip() or "unknown"
    title = str(raw.get("title") or "").strip()
    content = str(raw.get("content") or "").strip()
    return {
        "doc_id": doc_id,
        "source_type": source_type,
        "title": title,
        "content": content,
        "metadata": {
            "source_type": source_type,
            "original_doc_id": doc_id,
            "title": title,
        },
    }


def sample_documents(
    input_path: Path,
    output_path: Path,
    limit: int,
    per_source_limit: int,
    min_content_chars: int,
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    per_source_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    skipped = Counter()

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            if len(selected) >= limit:
                break
            if not line.strip():
                continue
            try:
                normalized = _normalize_document(json.loads(line))
            except json.JSONDecodeError:
                skipped["json_decode_error"] += 1
                continue

            doc_id = normalized["doc_id"]
            source_type = normalized["source_type"]
            content = normalized["content"]
            if not doc_id or doc_id in seen_ids:
                skipped["missing_or_duplicate_doc_id"] += 1
                continue
            if len(content) < min_content_chars:
                skipped["short_content"] += 1
                continue
            if per_source_counts[source_type] >= per_source_limit:
                skipped["source_limit"] += 1
                continue

            selected.append(normalized)
            seen_ids.add(doc_id)
            per_source_counts[source_type] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for doc in selected:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    summary = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "requested_limit": limit,
        "per_source_limit": per_source_limit,
        "min_content_chars": min_content_chars,
        "selected_count": len(selected),
        "source_counts": dict(sorted(per_source_counts.items())),
        "skipped": dict(skipped),
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample EnterpriseRAG-Bench documents.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--per-source-limit", type=int, default=250)
    parser.add_argument("--min-content-chars", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = sample_documents(
        input_path=args.input,
        output_path=args.output,
        limit=args.limit,
        per_source_limit=args.per_source_limit,
        min_content_chars=args.min_content_chars,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
