"""Export Enterprise KG nodes/relations into Neo4j import-friendly CSV files."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project.backend.knowledge_graph.graph_builder import load_nodes, load_relations
from project.backend.knowledge_graph.neo4j_client import render_constraints_cypher


DEFAULT_KG_DIR = WORKSPACE_ROOT / "data" / "processed" / "enterprise_kg"
DEFAULT_OUTPUT_DIR = DEFAULT_KG_DIR / "neo4j_import"


def export_neo4j_files(kg_dir: Path, output_dir: Path) -> dict:
    nodes = load_nodes(kg_dir / "nodes.jsonl")
    relations = load_relations(kg_dir / "relations.jsonl")
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes_csv = output_dir / "nodes.csv"
    with nodes_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["node_id:ID", "name", "type:LABEL", "properties"])
        writer.writeheader()
        for node in nodes:
            writer.writerow(
                {
                    "node_id:ID": node.node_id,
                    "name": node.name,
                    "type:LABEL": node.type.value,
                    "properties": json.dumps(node.properties, ensure_ascii=False),
                }
            )

    relations_csv = output_dir / "relations.csv"
    with relations_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=[":START_ID", ":END_ID", ":TYPE", "properties"])
        writer.writeheader()
        for relation in relations:
            writer.writerow(
                {
                    ":START_ID": relation.source_id,
                    ":END_ID": relation.target_id,
                    ":TYPE": relation.type.value,
                    "properties": json.dumps(relation.properties, ensure_ascii=False),
                }
            )

    constraints_path = output_dir / "constraints.cypher"
    constraints_path.write_text(render_constraints_cypher() + "\n", encoding="utf-8")

    summary = {
        "output_dir": str(output_dir),
        "node_count": len(nodes),
        "relation_count": len(relations),
        "files": {
            "nodes_csv": str(nodes_csv),
            "relations_csv": str(relations_csv),
            "constraints_cypher": str(constraints_path),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Enterprise KG Neo4j import files.")
    parser.add_argument("--kg-dir", type=Path, default=DEFAULT_KG_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = export_neo4j_files(args.kg_dir, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
