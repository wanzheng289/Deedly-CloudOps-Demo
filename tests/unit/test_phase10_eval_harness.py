from eval_harness.metrics.faithfulness import answer_faithfulness
from eval_harness.metrics.kg import kg_query_accuracy
from eval_harness.metrics.memory import memory_usefulness
from eval_harness.metrics.tool_call import tool_call_accuracy
from eval_harness.runners.run_eval import aggregate, evaluate_case, load_cases


def test_phase10_metrics():
    assert tool_call_accuracy(["a", "b"], ["b", "a"]) == 1.0
    assert kg_query_accuracy(
        [{"source_id": "a", "target_id": "b", "type": "REL"}],
        [{"source_id": "a", "target_id": "b", "type": "REL"}],
    ) == 1.0
    assert answer_faithfulness("SSO access requires entitlement sync", ["entitlement sync"]) > 0
    assert memory_usefulness(["SSO"], [{"product": "SSO"}]) == 1.0


def test_run_eval_customer_support_case():
    case = load_cases("customer_support_cases", limit=1)[0]
    result = evaluate_case("customer_support_cases", case, top_k=5, run_retrieval=False)
    summary = aggregate([result])

    assert result["dataset"] == "customer_support_cases"
    assert result["tool_call_accuracy"] == 1.0
    assert summary["case_count"] == 1


def test_run_eval_enterprise_kg_case():
    case = load_cases("enterprise_kg_cases", limit=1)[0]
    result = evaluate_case("enterprise_kg_cases", case, top_k=5, run_retrieval=False)

    assert result["dataset"] == "enterprise_kg_cases"
    assert result["kg_query_accuracy"] == 1.0


def test_run_eval_multidoc_case():
    case = load_cases("multidoc_dialogue_cases", limit=1)[0]
    result = evaluate_case("multidoc_dialogue_cases", case, top_k=5, run_retrieval=False)

    assert result["dataset"] == "multidoc_dialogue_cases"
    assert result["tool_call_accuracy"] == 1.0
