"""Validate normalized enterprise migration JSONL files.

This is the first gate of the migration pipeline. It checks that external
company data has been mapped into the standard schema before indexing RAG,
building the Enterprise KG, seeding Memory, or generating eval cases.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_DIR = WORKSPACE_ROOT / "data" / "migration" / "standard"
DEFAULT_SUMMARY = WORKSPACE_ROOT / "data" / "migration" / "validation_summary.json"

SCHEMA_FILES = {
    "documents": "documents.jsonl",
    "customers": "customers.jsonl",
    "tickets": "tickets.jsonl",
    "products_services": "products_services.jsonl",
    "relations": "relations.jsonl",
}

REQUIRED_FIELDS = {
    "documents": {"doc_id", "title", "content", "source_type"},
    "customers": {"customer_id", "name"},
    "tickets": {"ticket_id", "customer_id", "summary"},
    "products_services": {"entity_id", "name", "entity_type"},
    "relations": {"source_id", "source_type", "target_id", "target_type", "relation_type"},
}

LIST_FIELDS = {
    "documents": {"tags", "acl"},
    "customers": {"products", "risk_tags"},
    "tickets": {"messages", "linked_doc_ids"},
    "products_services": {"runtime_envs", "dependencies", "runbook_doc_ids"},
    "relations": set(),
}

STRING_FIELDS = {
    "documents": {"doc_id", "title", "content", "source_type", "source_uri", "created_at", "updated_at", "owner_team", "product", "service"},
    "customers": {"customer_id", "name", "industry", "segment", "sla_tier", "priority_tier", "contact_preference", "last_seen_at", "summary"},
    "tickets": {"ticket_id", "customer_id", "product", "service", "issue_type", "status", "priority", "sentiment", "created_at", "updated_at", "summary", "resolution"},
    "products_services": {"entity_id", "name", "entity_type", "description", "owner_team", "repo"},
    "relations": {"source_id", "source_type", "target_id", "target_type", "relation_type", "evidence_doc_id", "evidence_text", "created_at"},
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _validate_record(schema: str, record: dict[str, Any], line_no: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    for field in sorted(REQUIRED_FIELDS[schema]):
        if field not in record or _is_blank(record.get(field)):
            issues.append({"line": line_no, "level": "error", "field": field, "message": "missing_required_field"})

    for field in sorted(LIST_FIELDS[schema]):
        if field in record and record[field] is not None and not isinstance(record[field], list):
            issues.append({"line": line_no, "level": "error", "field": field, "message": "expected_list"})

    for field in sorted(STRING_FIELDS[schema]):
        if field in record and record[field] is not None and not isinstance(record[field], str):
            issues.append({"line": line_no, "level": "warning", "field": field, "message": "expected_string"})

    if schema == "relations":
        confidence = record.get("confidence")
        if confidence is not None and not isinstance(confidence, (int, float)):
            issues.append({"line": line_no, "level": "warning", "field": "confidence", "message": "expected_number"})

    return issues


def validate_jsonl(path: Path, schema: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema": schema,
        "path": str(path),
        "exists": path.exists(),
        "records": 0,
        "errors": 0,
        "warnings": 0,
        "issues": [],
    }
    if not path.exists():
        summary["errors"] = 1
        summary["issues"].append({"line": 0, "level": "error", "field": "", "message": "file_not_found"})
        return summary

    seen_ids: set[str] = set()
    id_field = {
        "documents": "doc_id",
        "customers": "customer_id",
        "tickets": "ticket_id",
        "products_services": "entity_id",
    }.get(schema)

    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue
            summary["records"] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                summary["issues"].append({"line": line_no, "level": "error", "field": "", "message": f"json_decode_error:{exc.msg}"})
                continue

            if not isinstance(record, dict):
                summary["issues"].append({"line": line_no, "level": "error", "field": "", "message": "expected_object"})
                continue

            summary["issues"].extend(_validate_record(schema, record, line_no))

            if id_field:
                value = str(record.get(id_field) or "").strip()
                if value:
                    if value in seen_ids:
                        summary["issues"].append({"line": line_no, "level": "error", "field": id_field, "message": "duplicate_id"})
                    seen_ids.add(value)

    level_counts = Counter(issue["level"] for issue in summary["issues"])
    summary["errors"] = level_counts["error"]
    summary["warnings"] = level_counts["warning"]
    return summary


def validate_directory(input_dir: Path, schemas: list[str]) -> dict[str, Any]:
    files = [schema for schema in schemas if schema in SCHEMA_FILES]
    results = [validate_jsonl(input_dir / SCHEMA_FILES[schema], schema) for schema in files]
    return {
        "input_dir": str(input_dir),
        "schemas": files,
        "ok": all(item["errors"] == 0 for item in results),
        "total_records": sum(item["records"] for item in results),
        "total_errors": sum(item["errors"] for item in results),
        "total_warnings": sum(item["warnings"] for item in results),
        "files": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate normalized enterprise migration JSONL files.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--schemas", nargs="+", default=list(SCHEMA_FILES), choices=sorted(SCHEMA_FILES))
    parser.add_argument("--no-write-summary", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_directory(args.input_dir, args.schemas)
    if not args.no_write_summary:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
