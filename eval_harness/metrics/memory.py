from __future__ import annotations


def memory_usefulness(expected_memory_keys: list[str], retrieved_memory: list[dict]) -> float:
    """Score whether retrieved memory/profile items cover expected keywords."""
    expected = [item.lower() for item in expected_memory_keys if item]
    if not expected:
        return 1.0
    blob = "\n".join(str(item) for item in retrieved_memory).lower()
    hits = sum(1 for item in expected if item in blob)
    return hits / len(expected)
