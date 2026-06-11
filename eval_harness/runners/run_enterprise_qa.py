"""Run Enterprise QA eval cases.

Default mode validates the dataset and writes a report skeleton. Pass
`--run-retrieval` to execute the current retriever and compute Recall@K.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from project.eval_harness.metrics.citation import citation_coverage
from project.eval_harness.metrics.latency import measure_latency
from project.eval_harness.metrics.retrieval import (
    extract_retrieved_doc_ids,
    hit_doc_ids,
    recall_at_k,
)


DEFAULT_DATASET = PROJECT_ROOT / "eval_harness" / "datasets" / "enterprise_qa.jsonl"
DEFAULT_REPORT = PROJECT_ROOT / "eval_harness" / "reports" / "enterprise_qa_report.json"


def load_cases(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if limit is not None and len(cases) >= limit:
                break
            if line.strip():
                cases.append(json.loads(line))
    return cases


def _retrieve(query: str, top_k: int) -> tuple[list[dict], float]:
    from project.backend.rag.retriever import retrieve_documents

    with measure_latency() as timer:
        result = retrieve_documents(query, top_k=top_k)
    return result.get("docs", []), timer.elapsed_ms


def evaluate_case(case: dict[str, Any], top_k: int, run_retrieval: bool) -> dict[str, Any]:
    retrieved_docs: list[dict] = []
    latency_ms = 0.0
    retrieval_error = ""
    if run_retrieval:
        try:
            retrieved_docs, latency_ms = _retrieve(case["user_query"], top_k=top_k)
        except Exception as exc:
            retrieval_error = str(exc)

    retrieved_doc_ids = extract_retrieved_doc_ids(retrieved_docs)
    expected_doc_ids = case.get("expected_doc_ids", [])
    recall = recall_at_k(expected_doc_ids, retrieved_doc_ids, top_k) if run_retrieval else None

    # Phase 3 does not generate final answers yet. Citation score is wired for
    # later phases and remains None until an answer is supplied.
    generated_answer = case.get("generated_answer", "")
    citation = (
        citation_coverage(generated_answer, retrieved_doc_ids)
        if run_retrieval and generated_answer
        else None
    )

    return {
        "case_id": case.get("case_id"),
        "question_type": case.get("question_type"),
        "source_types": case.get("source_types", []),
        "expected_doc_ids": expected_doc_ids,
        "retrieved_doc_ids": retrieved_doc_ids,
        "hit_doc_ids": hit_doc_ids(expected_doc_ids, retrieved_doc_ids, top_k) if run_retrieval else [],
        "retrieval_recall_at_k": recall,
        "citation_coverage": citation,
        "latency_ms": latency_ms if run_retrieval else None,
        "retrieval_error": retrieval_error,
    }


def aggregate(results: list[dict[str, Any]], run_retrieval: bool) -> dict[str, Any]:
    recall_values = [
        item["retrieval_recall_at_k"]
        for item in results
        if item.get("retrieval_recall_at_k") is not None
    ]
    citation_values = [
        item["citation_coverage"]
        for item in results
        if item.get("citation_coverage") is not None
    ]
    latency_values = [
        item["latency_ms"]
        for item in results
        if item.get("latency_ms") is not None
    ]
    errors = [item for item in results if item.get("retrieval_error")]
    return {
        "evaluated_with_retrieval": run_retrieval,
        "case_count": len(results),
        "retrieval_recall_at_k": mean(recall_values) if recall_values else None,
        "citation_coverage": mean(citation_values) if citation_values else None,
        "average_latency_ms": mean(latency_values) if latency_values else None,
        "retrieval_error_count": len(errors),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Enterprise QA eval.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--run-retrieval", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.dataset, limit=args.limit)
    results = [
        evaluate_case(case=case, top_k=args.top_k, run_retrieval=args.run_retrieval)
        for case in cases
    ]
    report = {
        "dataset": str(args.dataset),
        "top_k": args.top_k,
        "limit": args.limit,
        "summary": aggregate(results, run_retrieval=args.run_retrieval),
        "cases": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote report to {args.report}")


if __name__ == "__main__":
    main()
