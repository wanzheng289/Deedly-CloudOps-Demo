from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_servers.common import ToolRegistry, PROJECT_ROOT

try:
    from project.eval_harness.metrics.citation import citation_coverage
    from project.eval_harness.runners.run_eval import DATASET_FILES, aggregate, evaluate_case, load_cases
except ModuleNotFoundError:
    from eval_harness.metrics.citation import citation_coverage
    from eval_harness.runners.run_eval import DATASET_FILES, aggregate, evaluate_case, load_cases


registry = ToolRegistry("eval_mcp")
DEFAULT_REPORT_DIR = PROJECT_ROOT / "eval_harness" / "reports"


@registry.tool(description="Run an eval dataset and write a report.")
def run_eval_dataset(dataset: str = "enterprise_qa", limit: int = 50, top_k: int = 5, run_retrieval: bool = False) -> dict[str, Any]:
    if dataset not in DATASET_FILES:
        return {"ok": False, "error": f"unsupported_dataset:{dataset}"}
    cases = load_cases(dataset, limit=limit)
    results = [evaluate_case(dataset, case, top_k=top_k, run_retrieval=run_retrieval) for case in cases]
    report = {
        "dataset": dataset,
        "dataset_path": str(DATASET_FILES[dataset]),
        "top_k": top_k,
        "limit": limit,
        "summary": aggregate(results),
        "cases": results,
    }
    report_path = DEFAULT_REPORT_DIR / f"mcp_{dataset}_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "report_path": str(report_path), "summary": report["summary"]}


@registry.tool(description="Score an answer against retrieved document ids and required citations.")
def score_answer(answer: str, retrieved_doc_ids: list[str], required_doc_ids: list[str] | None = None) -> dict[str, Any]:
    required_doc_ids = required_doc_ids or []
    cited_score = citation_coverage(answer, retrieved_doc_ids)
    required_hits = sorted(set(required_doc_ids) & set(retrieved_doc_ids))
    return {
        "citation_coverage": cited_score,
        "required_doc_hit_count": len(required_hits),
        "required_doc_hits": required_hits,
    }


@registry.tool(description="Compare two prompt versions with simple metadata and recommendation.")
def compare_prompt_versions(prompt_a: str, prompt_b: str, metric_a: float = 0.0, metric_b: float = 0.0) -> dict[str, Any]:
    winner = "prompt_b" if metric_b > metric_a else "prompt_a" if metric_a > metric_b else "tie"
    return {
        "winner": winner,
        "metric_a": metric_a,
        "metric_b": metric_b,
        "length_a": len(prompt_a),
        "length_b": len(prompt_b),
        "recommendation": "choose higher metric; if tied, prefer shorter prompt for latency/cost",
    }


if __name__ == "__main__":
    registry.cli()
