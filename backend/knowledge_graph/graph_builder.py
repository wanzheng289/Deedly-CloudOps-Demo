"""Enterprise KG build and local graph utilities."""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

try:
    from project.backend.knowledge_graph.schema import KGNode, KGRelation
except ModuleNotFoundError:
    from backend.knowledge_graph.schema import KGNode, KGRelation


def _model_to_dict(item: KGNode | KGRelation) -> dict[str, Any]:
    return item.dict() if hasattr(item, "dict") else item.model_dump()


def _parse_node(payload: dict[str, Any]) -> KGNode:
    return KGNode.parse_obj(payload) if hasattr(KGNode, "parse_obj") else KGNode.model_validate(payload)


def _parse_relation(payload: dict[str, Any]) -> KGRelation:
    return KGRelation.parse_obj(payload) if hasattr(KGRelation, "parse_obj") else KGRelation.model_validate(payload)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_nodes(path: Path) -> list[KGNode]:
    """Load normalized KG nodes from JSONL."""
    return [_parse_node(row) for row in read_jsonl(path)]


def load_relations(path: Path) -> list[KGRelation]:
    """Load normalized KG relations from JSONL."""
    return [_parse_relation(row) for row in read_jsonl(path)]


def dedupe_nodes(nodes: Iterable[KGNode]) -> list[KGNode]:
    merged: dict[str, KGNode] = {}
    for node in nodes:
        existing = merged.get(node.node_id)
        if not existing:
            merged[node.node_id] = node
            continue
        existing.properties.update({k: v for k, v in node.properties.items() if v not in (None, "", [], {})})
    return sorted(merged.values(), key=lambda node: (node.type.value, node.node_id))


def dedupe_relations(relations: Iterable[KGRelation]) -> list[KGRelation]:
    merged: dict[tuple[str, str, str], KGRelation] = {}
    for relation in relations:
        key = (relation.source_id, relation.target_id, relation.type.value)
        existing = merged.get(key)
        if not existing:
            merged[key] = relation
            continue
        existing.properties.update({k: v for k, v in relation.properties.items() if v not in (None, "", [], {})})
    return sorted(merged.values(), key=lambda rel: (rel.type.value, rel.source_id, rel.target_id))


def save_nodes(path: Path, nodes: Iterable[KGNode]) -> int:
    return write_jsonl(path, (_model_to_dict(node) for node in dedupe_nodes(nodes)))


def save_relations(path: Path, relations: Iterable[KGRelation]) -> int:
    return write_jsonl(path, (_model_to_dict(relation) for relation in dedupe_relations(relations)))


class LocalEnterpriseGraph:
    """Small in-memory graph used before Neo4j is running."""

    def __init__(self, nodes: list[KGNode], relations: list[KGRelation]) -> None:
        self.nodes_by_id = {node.node_id: node for node in nodes}
        self.relations = relations
        self.name_index: dict[str, set[str]] = defaultdict(set)
        self.adjacency: dict[str, list[KGRelation]] = defaultdict(list)
        self.reverse_adjacency: dict[str, list[KGRelation]] = defaultdict(list)
        for node in nodes:
            self.name_index[node.name.lower()].add(node.node_id)
            self.name_index[node.node_id.lower()].add(node.node_id)
        for relation in relations:
            self.adjacency[relation.source_id].append(relation)
            self.reverse_adjacency[relation.target_id].append(relation)

    def find_node_ids(self, entity: str) -> list[str]:
        entity_l = entity.lower().strip()
        if not entity_l:
            return []
        exact = set(self.name_index.get(entity_l, set()))
        fuzzy = {
            node_id
            for node_id, node in self.nodes_by_id.items()
            if entity_l in node.name.lower() or entity_l in node_id.lower()
        }
        return sorted(exact | fuzzy)

    def neighborhood(self, entity: str, relation_type: str | None = None, depth: int = 2, limit: int = 80) -> dict[str, Any]:
        start_ids = self.find_node_ids(entity)
        visited = set(start_ids)
        queue = deque((node_id, 0) for node_id in start_ids)
        out_relations: list[KGRelation] = []

        while queue and len(out_relations) < limit:
            node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for relation in self.adjacency.get(node_id, []) + self.reverse_adjacency.get(node_id, []):
                if relation_type and relation.type.value != relation_type:
                    continue
                out_relations.append(relation)
                next_id = relation.target_id if relation.source_id == node_id else relation.source_id
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, current_depth + 1))

        node_ids = set(start_ids)
        for relation in out_relations:
            node_ids.add(relation.source_id)
            node_ids.add(relation.target_id)
        return {
            "query": {"entity": entity, "relation_type": relation_type, "depth": depth},
            "nodes": [_model_to_dict(self.nodes_by_id[node_id]) for node_id in sorted(node_ids) if node_id in self.nodes_by_id],
            "relations": [_model_to_dict(relation) for relation in out_relations],
        }


def load_local_graph(nodes_path: Path, relations_path: Path) -> LocalEnterpriseGraph:
    return LocalEnterpriseGraph(load_nodes(nodes_path), load_relations(relations_path))
