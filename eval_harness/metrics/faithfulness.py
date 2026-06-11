from __future__ import annotations

import re


def answer_faithfulness(answer: str, answer_facts: list[str]) -> float:
    """Simple lexical fact coverage score for first-pass offline eval."""
    facts = [fact for fact in answer_facts if fact]
    if not facts:
        return 1.0
    answer_terms = _terms(answer)
    if not answer_terms:
        return 0.0
    scores = []
    for fact in facts:
        fact_terms = _terms(fact)
        if not fact_terms:
            continue
        scores.append(len(answer_terms & fact_terms) / len(fact_terms))
    return sum(scores) / len(scores) if scores else 0.0


def _terms(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[a-zA-Z0-9_\-]+", text or "") if len(token) >= 3}
