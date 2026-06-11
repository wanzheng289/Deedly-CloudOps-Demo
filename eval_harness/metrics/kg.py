from __future__ import annotations


def kg_query_accuracy(expected_relations: list[dict], actual_relations: list[dict]) -> float:
    """Score whether expected KG relation triples appear in actual graph relations."""
    if not expected_relations:
        return 1.0
    actual = {
        (
            relation.get("source_id"),
            relation.get("target_id"),
            relation.get("type"),
        )
        for relation in actual_relations
    }
    hits = 0
    for expected in expected_relations:
        triple = (
            expected.get("source_id"),
            expected.get("target_id"),
            expected.get("type"),
        )
        if triple in actual:
            hits += 1
    return hits / len(expected_relations)
