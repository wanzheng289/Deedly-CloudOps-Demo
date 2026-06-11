from __future__ import annotations


def tool_call_accuracy(expected_tools: list[str], actual_tools: list[str]) -> float:
    """Return fraction of expected tools present in the actual tool sequence."""
    expected = [tool for tool in expected_tools if tool]
    if not expected:
        return 1.0
    actual = set(tool for tool in actual_tools if tool)
    hits = sum(1 for tool in expected if tool in actual)
    return hits / len(expected)


def exact_tool_sequence_match(expected_tools: list[str], actual_tools: list[str]) -> float:
    return 1.0 if expected_tools == actual_tools[: len(expected_tools)] else 0.0
