"""Build Enterprise QA eval cases from EnterpriseRAG-Bench questions."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = WORKSPACE_ROOT / "data" / "raw" / "enterprise_rag_bench" / "questions.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "eval_harness" / "datasets" / "enterprise_qa.jsonl"


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _to_eval_case(raw: dict[str, Any]) -> dict[str, Any]:
    case_id = str(raw.get("question_id") or "").strip()
    question = str(raw.get("question") or "").strip()
    source_types = _normalize_list(raw.get("source_types"))
    expected_doc_ids = _normalize_list(raw.get("expected_doc_ids"))
    return {
        "case_id": case_id,
        "question_type": str(raw.get("question_type") or "unknown").strip() or "unknown",
        "user_query": question,
        "expected_tools": ["search_enterprise_kb"],
        "expected_doc_ids": expected_doc_ids,
        "reference_answer": str(raw.get("gold_answer") or "").strip(),
        "answer_facts": _normalize_list(raw.get("answer_facts")),
        "source_types": source_types,
        "risk_level": "normal",
        "metadata": {
            "source_dataset": "EnterpriseRAG-Bench",
            "original_question_id": case_id,
        },
    }


def build_enterprise_qa(input_path: Path, output_path: Path, limit: int | None = None) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    written = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
        for line in src:
            if limit is not None and written >= limit:
                break
            if not line.strip():
                continue
            raw = json.loads(line)
            case = _to_eval_case(raw)
            if not case["case_id"] or not case["user_query"]:
                counts["skipped_missing_required"] += 1
                continue
            dst.write(json.dumps(case, ensure_ascii=False) + "\n")
            written += 1
            counts[f"question_type:{case['question_type']}"] += 1
            for source_type in case["source_types"]:
                counts[f"source_type:{source_type}"] += 1

    summary = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "limit": limit,
        "written": written,
        "counts": dict(sorted(counts.items())),
    }
    output_path.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Enterprise QA eval dataset.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_enterprise_qa(args.input, args.output, args.limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
