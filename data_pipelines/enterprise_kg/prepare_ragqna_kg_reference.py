"""Prepare RAGQnASystem KG reference data.

This is not a medical plugin for the enterprise agent. It keeps a normalized
reference output from RAGQnASystem so the Enterprise KG pipeline can reuse the
same engineering pattern: entity schema, relation schema, Neo4j import, and
KG query tooling.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ENTITY_TYPES = [
    "疾病",
    "药品",
    "食物",
    "检查项目",
    "科目",
    "疾病症状",
    "治疗方法",
    "药品商",
]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [_normalize_text(value)] if _normalize_text(value) else []
    out: list[str] = []
    for item in value:
        if isinstance(item, list):
            item = item[0] if item else ""
        text = _normalize_text(item)
        if text.endswith("..."):
            text = text[:-3]
        if len(text) >= 1:
            out.append(text)
    return out


def load_medical_records(input_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip().rstrip(",")
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                try:
                    records.append(ast.literal_eval(raw))
                except (SyntaxError, ValueError):
                    # Keep the pipeline usable if a single record is malformed.
                    continue
    return records


def extract_entities_and_relations(records: list[dict[str, Any]]) -> tuple[dict[str, list[Any]], list[tuple[str, str, str, str, str]]]:
    entities: dict[str, list[Any]] = {entity_type: [] for entity_type in ENTITY_TYPES}
    relations: list[tuple[str, str, str, str, str]] = []

    for data in records:
        disease_name = _normalize_text(data.get("name"))
        if not disease_name:
            continue

        entities["疾病"].append(
            {
                "名称": disease_name,
                "疾病简介": _normalize_text(data.get("desc")),
                "疾病病因": _normalize_text(data.get("cause")),
                "预防措施": _normalize_text(data.get("prevent")),
                "治疗周期": _normalize_text(data.get("cure_lasttime")),
                "治愈概率": _normalize_text(data.get("cured_prob")),
                "疾病易感人群": _normalize_text(data.get("easy_get")),
            }
        )

        drugs = _normalize_list(data.get("common_drug")) + _normalize_list(data.get("recommand_drug"))
        entities["药品"].extend(drugs)
        relations.extend(("疾病", disease_name, "疾病使用药品", "药品", drug) for drug in drugs)

        do_eat = _normalize_list(data.get("do_eat")) + _normalize_list(data.get("recommand_eat"))
        no_eat = _normalize_list(data.get("not_eat"))
        entities["食物"].extend(do_eat + no_eat)
        relations.extend(("疾病", disease_name, "疾病宜吃食物", "食物", food) for food in do_eat)
        relations.extend(("疾病", disease_name, "疾病忌吃食物", "食物", food) for food in no_eat)

        checks = _normalize_list(data.get("check"))
        entities["检查项目"].extend(checks)
        relations.extend(("疾病", disease_name, "疾病所需检查", "检查项目", check) for check in checks)

        departments = _normalize_list(data.get("cure_department"))
        entities["科目"].extend(departments)
        if departments:
            relations.append(("疾病", disease_name, "疾病所属科目", "科目", departments[-1]))

        symptoms = _normalize_list(data.get("symptom"))
        entities["疾病症状"].extend(symptoms)
        relations.extend(("疾病", disease_name, "疾病的症状", "疾病症状", symptom) for symptom in symptoms)

        cure_ways = [item for item in _normalize_list(data.get("cure_way")) if len(item) >= 2]
        entities["治疗方法"].extend(cure_ways)
        relations.extend(("疾病", disease_name, "治疗的方法", "治疗方法", cure_way) for cure_way in cure_ways)

        complications = _normalize_list(data.get("acompany"))
        relations.extend(("疾病", disease_name, "疾病并发疾病", "疾病", disease) for disease in complications)

        for detail in _normalize_list(data.get("drug_detail")):
            parts = [part.strip() for part in detail.split(",")]
            if len(parts) != 2:
                continue
            drug, producer = parts
            if not drug or not producer:
                continue
            entities["药品"].append(drug)
            entities["药品商"].append(producer)
            relations.append(("药品商", producer, "生产", "药品", drug))

    deduped_entities: dict[str, list[Any]] = {}
    for entity_type, values in entities.items():
        if entity_type == "疾病":
            seen = set()
            out = []
            for value in values:
                name = value["名称"]
                if name in seen:
                    continue
                seen.add(name)
                out.append(value)
            deduped_entities[entity_type] = out
        else:
            deduped_entities[entity_type] = sorted(set(_normalize_text(item) for item in values if _normalize_text(item)))

    deduped_relations = sorted(set(rel for rel in relations if len(rel) == 5 and all(rel)))
    return deduped_entities, deduped_relations


def write_outputs(
    entities: dict[str, list[Any]],
    relations: list[tuple[str, str, str, str, str]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    entities_dir = output_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    for entity_type, values in entities.items():
        path = entities_dir / f"{entity_type}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for value in values:
                payload = value if isinstance(value, dict) else {"名称": value}
                payload = {"entity_type": entity_type, **payload}
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    with (output_dir / "relations.jsonl").open("w", encoding="utf-8") as f:
        for source_type, source_name, relation, target_type, target_name in relations:
            payload = {
                "source_type": source_type,
                "source_name": source_name,
                "relation": relation,
                "target_type": target_type,
                "target_name": target_name,
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    summary = {
        "entity_counts": {key: len(value) for key, value in entities.items()},
        "relation_count": len(relations),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare medical KG data for the Agent plugin.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("RAGQnASystem/data/medical_new_2.json"),
        help="Path to RAGQnASystem medical_new_2.json JSONL file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/ragqna_kg_reference"),
        help="Directory for normalized RAGQnASystem KG reference outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_medical_records(args.input)
    entities, relations = extract_entities_and_relations(records)
    write_outputs(entities, relations, args.output_dir)
    print(f"Wrote RAGQnASystem KG reference data to {args.output_dir}")


if __name__ == "__main__":
    main()
