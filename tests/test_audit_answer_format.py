from scripts.audit_answer_format import format_audit_answer, llm_total_tokens


def test_format_audit_answer_places_token_after_data_cutoff():
    answer = "\n".join(
        [
            "结果如下。",
            "",
            "数据截至 2026-05-12。",
            "",
            "查询起始时间：2026-05-13T00:00:00Z",
            "查询结束时间：2026-05-13T00:00:01Z",
        ]
    )

    formatted = format_audit_answer(answer, total_tokens=168)

    assert formatted.splitlines() == ["结果如下。", "", "数据截至 2026-05-12。", "LLM token：168"]


def test_format_audit_answer_moves_existing_token_after_cutoff():
    answer = "\n".join(
        [
            "结果如下。",
            "",
            "LLM token：168",
            "",
            "数据结束日：2026-05-11",
        ]
    )

    formatted = format_audit_answer(answer, total_tokens=200)

    assert formatted.splitlines() == ["结果如下。", "", "数据结束日：2026-05-11", "LLM token：168"]


def test_llm_total_tokens_collects_nested_usage_once_per_usage_record():
    result = {
        "v3": {"llm_usage": [{"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}]},
        "result": {"llm_usage": [{"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}]},
    }

    assert llm_total_tokens(result) == 25


def test_llm_total_tokens_defaults_to_zero_when_no_llm_usage():
    assert llm_total_tokens({"answer": "拒答"}) == 0
