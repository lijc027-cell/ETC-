from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from etf_agent.realtime_registry import get_realtime_registry, validate_realtime_registry
from etf_agent.realtime_runtime import execute_realtime_plan, fake_realtime_result, run_realtime_query
from etf_agent.v3 import semantic_query_v3


def test_realtime_registry_validates_default_shape():
    registry = get_realtime_registry()

    validate_realtime_registry(registry)

    assert set(registry["intent_to_scenario_matrix"]) >= {
        "overview",
        "price_change",
        "trading",
        "valuation",
        "order_book",
        "trade_flow",
    }
    assert set(registry["scenario_to_fields_matrix"]["trading"]) == {
        "amount",
        "volume",
        "latestVolume",
        "tradeTime",
    }


def test_v3_5_realtime_uses_registry_scenario_mutation():
    registry = deepcopy(get_realtime_registry())
    registry["intent_to_scenario_matrix"]["price_change"]["any_of"] = ["报价"]

    result = run_realtime_query(
        "510050报价",
        config_obj=SimpleNamespace(),
        dry_run=True,
        registry=registry,
    )

    assert result["v3"]["routing_result"] == {"type": "ExecutableQuery", "reason": None}
    assert result["query_plan"]["scenarios"] == ["price_change"]
    assert result["query_plan"]["fields"] == ["latest", "change", "changeRatio", "tradeTime"]


def test_v3_5_realtime_uses_registry_field_display_mutation():
    registry = deepcopy(get_realtime_registry())
    registry["field_display_matrix"]["amount"]["scale_value"] = 10_000
    registry["field_display_matrix"]["amount"]["unit_value"] = "万元"

    result = run_realtime_query(
        "510050成交额多少",
        config_obj=SimpleNamespace(),
        dry_run=True,
        registry=registry,
    )

    assert "当前成交额为 125000.00万元" in result["answer"]


@pytest.mark.parametrize(
    ("question", "expected_scenarios", "expected_fields"),
    [
        ("510050现在什么价", ["price_change"], ["latest", "tradeTime"]),
        ("510050成交额多少", ["trading"], ["amount", "tradeTime"]),
        ("510050盘口", ["order_book"], ["bid1", "ask1", "bidSize1", "askSize1", "tradeTime"]),
        ("510050溢价多少", ["valuation"], ["premium", "tradeTime"]),
        ("510050内外盘", ["trade_flow"], ["sellVolume", "buyVolume", "tradeTime"]),
        ("510050振幅多大", ["overview"], ["swing", "tradeTime"]),
    ],
)
def test_v3_5_realtime_supported_scenarios(question, expected_scenarios, expected_fields):
    result = run_realtime_query(question, config_obj=SimpleNamespace(), dry_run=True)

    assert result["v3"]["phase"] == "v3.5"
    assert result["v3"]["recognized_query_mode"] == "realtime"
    assert result["query_plan"]["scenarios"] == expected_scenarios
    assert result["query_plan"]["fields"] == expected_fields
    assert result["answer"]


def test_v3_5_realtime_composes_multiple_registry_scenarios():
    result = run_realtime_query("510050涨了没，成交额多少", config_obj=SimpleNamespace(), dry_run=True)

    assert result["query_plan"]["scenarios"] == ["price_change", "trading"]
    assert result["query_plan"]["fields"] == ["change", "changeRatio", "amount", "tradeTime"]


def test_v3_5_realtime_trade_flow_formats_ratio_and_scaled_volumes():
    result = run_realtime_query("510050内外盘", config_obj=SimpleNamespace(), dry_run=True)

    assert "外盘 61.00万手" in result["answer"]
    assert "内盘 52.00万手" in result["answer"]
    assert "外内盘比 1.17" in result["answer"]


def test_v3_5_realtime_valuation_formats_premium_as_percent():
    result = run_realtime_query("510050溢价多少", config_obj=SimpleNamespace(), dry_run=True)

    assert "折溢价率为 -0.17%" in result["answer"]


def test_v3_5_realtime_percent_fields_accept_already_percent_values():
    registry = get_realtime_registry()
    rule = registry["field_display_matrix"]["changeRatio"]

    from etf_agent.realtime_runtime import _format_realtime_value

    assert _format_realtime_value(-1.2687, rule) == "-1.27%"
    assert _format_realtime_value(-0.012687, rule) == "-1.27%"


def test_v3_5_realtime_keeps_common_etf_name_ambiguity_in_dry_run():
    result = run_realtime_query("科创50ETF报多少", config_obj=SimpleNamespace(), dry_run=True)

    assert result["v3"]["routing_result"] == {"type": "UnsupportedQuery", "reason": "fund_identity_ambiguous"}
    assert result["v3"]["routing_evidence"]["fund_resolution"]["status"] == "ambiguous"
    assert len(result["v3"]["routing_evidence"]["fund_resolution"]["matches"]) >= 2
    assert "我查到几只可能匹配的 ETF" in result["answer"]
    assert "588000" in result["answer"]
    assert "588080" in result["answer"]
    assert "你可以直接回基金代码" in result["answer"]


def test_v3_5_realtime_name_ambiguity_returns_candidates_without_remote_call(monkeypatch):
    called = False

    def fail_if_called(_plan):
        nonlocal called
        called = True
        raise AssertionError("ambiguous fund name should not call realtime source")

    monkeypatch.setattr("etf_agent.realtime_runtime.execute_realtime_plan", fail_if_called)

    result = run_realtime_query("沪深300ETF怎么样", config_obj=SimpleNamespace(), dry_run=True)

    assert called is False
    assert result["v3"]["routing_result"] == {"type": "UnsupportedQuery", "reason": "fund_identity_ambiguous"}
    assert result["v3"]["routing_evidence"]["fund_resolution"]["status"] == "ambiguous"
    assert len(result["v3"]["routing_evidence"]["fund_resolution"]["matches"]) >= 2


def test_v3_5_realtime_default_overview_uses_registry_config_and_clarifies():
    result = run_realtime_query("510050现在怎么样", config_obj=SimpleNamespace(), dry_run=True)

    assert result["query_plan"]["scenarios"] == ["default_overview"]
    assert result["query_plan"]["fields"] == ["latest", "change", "changeRatio", "amount", "tradeTime"]
    assert "先看核心实时情况：" in result["answer"]
    assert "实时行情：" not in result["answer"]
    assert "你还可以继续问价格涨跌、成交活跃、折溢价、盘口或内外盘。" in result["answer"]


def test_v3_5_realtime_single_answer_reads_like_an_answer():
    result = run_realtime_query("510050现在什么价", config_obj=SimpleNamespace(), dry_run=True)

    assert result["answer"].startswith("上证50ETF（510050）当前最新价")
    assert "实时行情：" not in result["answer"]
    assert "数据时间 14:56:03" in result["answer"]


def test_v3_5_realtime_single_field_answer_does_not_append_default_trading_fields():
    result = run_realtime_query("510050成交额多少", config_obj=SimpleNamespace(), dry_run=True)

    assert result["query_plan"]["fields"] == ["amount", "tradeTime"]
    assert "成交额" in result["answer"]
    assert result["answer"] == "上证50ETF（510050）当前成交额为 12.50亿元，数据时间 14:56:03。"
    assert "实时行情：" not in result["answer"]
    assert "成交量" not in result["answer"]
    assert "现手" not in result["answer"]


def test_v3_5_realtime_multi_field_answer_only_uses_explicit_fields():
    result = run_realtime_query("510050价格、涨跌幅、成交额、溢价率", config_obj=SimpleNamespace(), dry_run=True)

    assert result["query_plan"]["fields"] == ["latest", "changeRatio", "amount", "premium", "tradeTime"]
    assert result["answer"] == "上证50ETF（510050）当前最新价为 2.5123；涨跌幅 +0.49%，成交额 12.50亿元，折溢价率 -0.17%。数据时间 14:56:03。"
    assert "IOPV" not in result["answer"]
    assert "成交量" not in result["answer"]
    assert "现手" not in result["answer"]


def test_v3_5_realtime_order_book_includes_required_four_fields_without_full_dump():
    result = run_realtime_query("510050盘口", config_obj=SimpleNamespace(), dry_run=True)

    assert result["query_plan"]["fields"] == ["bid1", "ask1", "bidSize1", "askSize1", "tradeTime"]
    assert result["answer"] == "上证50ETF（510050）盘口上，买一价 2.512、卖一价 2.513；买一量 18000、卖一量 21000。数据时间 14:56:03。"
    assert "实时行情：" not in result["answer"]


def test_v3_5_realtime_ambiguous_fund_answer_uses_natural_clarification():
    result = run_realtime_query("科创50ETF报多少", config_obj=SimpleNamespace(), dry_run=True)

    assert result["v3"]["routing_result"] == {"type": "UnsupportedQuery", "reason": "fund_identity_ambiguous"}
    assert result["answer"].startswith("我查到几只可能匹配的 ETF，先列出来供你确认：")
    assert "你可以直接回基金代码，我再继续查实时数据。" in result["answer"]


def test_v3_5_realtime_real_mode_uses_llm_plan_and_records_tokens(monkeypatch):
    def fake_planner(**_kwargs):
        return {
            "raw": "{}",
            "draft": {
                "type": "executable_query",
                "subqueries": [
                    {
                        "id": "sq_1",
                        "intent_profile": "trading",
                        "metrics": [
                            {"field": "amount", "source": "explicit_user_request", "required": True},
                        ],
                        "time_scope": {"kind": "realtime"},
                        "presentation": "summary",
                    }
                ],
            },
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }

    monkeypatch.setattr("etf_agent.realtime_runtime.generate_realtime_plan_with_llm", fake_planner)
    monkeypatch.setattr("etf_agent.realtime_runtime.execute_realtime_plan", lambda plan: fake_realtime_result(plan))

    result = run_realtime_query("510050成交额多少", config_obj=SimpleNamespace(), dry_run=False)

    assert result["v3"]["ast_generation_mode"] == "realtime_llm_plan"
    assert result["llm_usage"] == [{"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}]
    assert result["query_plan"]["scenarios"] == ["trading"]
    assert result["query_plan"]["fields"] == ["amount", "tradeTime"]
    assert "成交额" in result["answer"]


def test_v3_5_realtime_real_mode_uses_llm_metrics_over_keyword_defaults(monkeypatch):
    def fake_planner(**_kwargs):
        return {
            "raw": "{}",
            "draft": {
                "type": "executable_query",
                "subqueries": [
                    {
                        "id": "sq_1",
                        "intent_profile": "valuation",
                        "metrics": [
                            {"field": "premium", "source": "explicit_user_request", "required": True},
                        ],
                        "time_scope": {"kind": "realtime"},
                        "presentation": "summary",
                    }
                ],
            },
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

    monkeypatch.setattr("etf_agent.realtime_runtime.generate_realtime_plan_with_llm", fake_planner)
    monkeypatch.setattr("etf_agent.realtime_runtime.execute_realtime_plan", lambda plan: fake_realtime_result(plan))

    result = run_realtime_query("510050现在什么价", config_obj=SimpleNamespace(), dry_run=False)

    assert result["query_plan"]["scenarios"] == ["price_change"]
    assert result["query_plan"]["fields"] == ["latest", "tradeTime"]
    assert "最新价" in result["answer"]
    assert "折溢价率" not in result["answer"]


def test_v3_5_realtime_real_mode_overview_llm_plan_uses_default_overview(monkeypatch):
    def fake_planner(**_kwargs):
        return {
            "raw": "{}",
            "draft": {
                "type": "executable_query",
                "subqueries": [
                    {
                        "id": "sq_1",
                        "intent_profile": "overview",
                        "metrics": [
                            {"field": "latest", "source": "default_profile", "required": True},
                            {"field": "change", "source": "default_profile", "required": True},
                            {"field": "changeRatio", "source": "default_profile", "required": True},
                            {"field": "amount", "source": "default_profile", "required": True},
                        ],
                        "time_scope": {"kind": "realtime"},
                        "presentation": "summary",
                    }
                ],
            },
            "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        }

    monkeypatch.setattr("etf_agent.realtime_runtime.generate_realtime_plan_with_llm", fake_planner)
    monkeypatch.setattr("etf_agent.realtime_runtime.execute_realtime_plan", lambda plan: fake_realtime_result(plan))

    result = run_realtime_query("510050现在怎么样", config_obj=SimpleNamespace(), dry_run=False)

    assert result["query_plan"]["scenarios"] == ["default_overview"]
    assert result["query_plan"]["fields"] == ["latest", "change", "changeRatio", "amount", "tradeTime"]
    assert result["llm_usage"] == [{"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13}]


def test_v3_5_realtime_compare_falls_back_to_registry_if_llm_plan_fails(monkeypatch):
    def fail_planner(**_kwargs):
        raise ValueError("bad realtime plan")

    monkeypatch.setattr("etf_agent.realtime_runtime.generate_realtime_plan_with_llm", fail_planner)
    monkeypatch.setattr("etf_agent.realtime_runtime.execute_realtime_plan", lambda plan: fake_realtime_result(plan))

    result = run_realtime_query("对比510050和510300的涨跌幅和溢价", config_obj=SimpleNamespace(), dry_run=False)

    assert result["v3"]["routing_result"] == {"type": "ExecutableQuery", "reason": None}
    assert result["query_plan"]["fundcodes"] == ["510050", "510300"]
    assert "涨跌幅" in result["answer"]
    assert "折溢价率" in result["answer"]


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("510300基金经理是谁", "unsupported_query"),
        ("贵州茅台现在什么价", "unsupported_domain"),
        ("上证指数多少点", "unsupported_domain"),
        ("510050五档盘口", "field_not_supported"),
        ("这只ETF盘口什么情况", "fund_identity_required"),
    ],
)
def test_v3_5_realtime_unsupported_questions_are_structured(question, reason):
    result = run_realtime_query(question, config_obj=SimpleNamespace(), dry_run=True)

    assert result["v3"]["routing_result"]["type"] == "UnsupportedQuery"
    assert result["v3"]["routing_result"]["reason"] == reason
    assert result["v3"]["remote_query_allowed"] is False
    assert result["failure_reason"] == reason


def test_semantic_query_v3_5_realtime_does_not_use_v3_4_denial_in_dry_run():
    result = semantic_query_v3("帮我查510300的实时行情", root=".", dry_run=True, phase="v3.5")

    assert result["v3"]["phase"] == "v3.5"
    assert result["v3"]["recognized_query_mode"] == "realtime"
    assert result["v3"]["v3_5_route_mode"] == "local_router"
    assert result["v3"]["v3_5_route"]["route"] == "realtime"
    assert result["v3"]["routing_result"] == {"type": "ExecutableQuery", "reason": None}
    assert "不提供实时行情" not in result["answer"]


def test_semantic_query_v3_5_real_mode_uses_llm_router_before_realtime(monkeypatch):
    def fake_router(**_kwargs):
        return {
            "raw": "{}",
            "route": {
                "route": "realtime",
                "reason": "user asks for current quote",
                "confidence": 0.91,
                "needs_fund_identity": False,
                "needs_clarification": False,
            },
            "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        }

    def fake_realtime(question, *, config_obj, dry_run):
        return {
            "question": question,
            "answer": "实时结果",
            "v3": {
                "phase": "v3.5",
                "recognized_query_mode": "realtime",
                "routing_result": {"type": "ExecutableQuery", "reason": None},
                "llm_usage": [],
            },
            "llm_usage": [],
        }

    monkeypatch.setattr("etf_agent.v3.generate_v3_5_route_with_llm", fake_router)
    monkeypatch.setattr("etf_agent.realtime_runtime.run_realtime_query", fake_realtime)

    result = semantic_query_v3("510050现在什么价", root=".", dry_run=False, phase="v3.5")

    assert result["answer"] == "实时结果"
    assert result["v3"]["v3_5_route_mode"] == "llm_router"
    assert result["v3"]["v3_5_route"]["route"] == "realtime"
    assert result["v3"]["v3_5_route_usage"] == {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18}
    assert result["llm_usage"] == [{"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18}]


def test_semantic_query_v3_5_normalizes_llm_router_unsupported_reason(monkeypatch):
    def fake_router(**_kwargs):
        return {
            "raw": "{}",
            "route": {
                "route": "unsupported",
                "reason": "上证指数不是ETF，且问题语义不完整",
                "confidence": 0.95,
                "needs_fund_identity": False,
                "needs_clarification": False,
            },
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }

    monkeypatch.setattr("etf_agent.v3.generate_v3_5_route_with_llm", fake_router)

    result = semantic_query_v3("上证指数多少点", root=".", dry_run=False, phase="v3.5")

    assert result["v3"]["routing_result"] == {"type": "UnsupportedQuery", "reason": "unsupported_domain"}
    assert result["v3"]["v3_5_route"]["reason"] == "上证指数不是ETF，且问题语义不完整"


def test_semantic_query_v3_5_pure_compare_returns_capability_clarification_dry_run():
    result = semantic_query_v3("对比510050和510300", root=".", dry_run=True, phase="v3.5")

    assert result["v3"]["routing_result"] == {"type": "ClarificationRequired", "reason": "capability_ambiguous"}
    assert result["v3"]["v3_5_route"]["route"] == "capability_clarify"
    assert "实时行情" in result["answer"]
    assert "基金资料" in result["answer"]
    assert "你想继续看实时行情对比，还是基金资料/收益/费率对比？" in result["answer"]


def test_semantic_query_v3_5_capability_clarification_uses_llm_router(monkeypatch):
    def fake_router(**_kwargs):
        return {
            "raw": "{}",
            "route": {
                "route": "capability_clarify",
                "reason": "both realtime and profile comparison are plausible",
                "confidence": 0.72,
                "needs_fund_identity": False,
                "needs_clarification": True,
            },
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        }

    monkeypatch.setattr("etf_agent.v3.generate_v3_5_route_with_llm", fake_router)

    result = semantic_query_v3("对比510050和510300", root=".", dry_run=False, phase="v3.5")

    assert result["v3"]["routing_result"] == {"type": "ClarificationRequired", "reason": "capability_ambiguous"}
    assert result["v3"]["v3_5_route_mode"] == "llm_router"
    assert result["v3"]["v3_5_route"]["route"] == "capability_clarify"
    assert result["llm_usage"] == [{"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12}]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("510050持仓哪些股票", "dry_run"),
        ("510300基金经理是谁", "基金经理"),
        ("510050费率多少", "管理费率"),
    ],
)
def test_semantic_query_v3_5_routes_non_realtime_info_to_mongo_dry_run(question, expected):
    result = semantic_query_v3(question, root=".", dry_run=True, phase="v3.5")

    assert result["v3"]["phase"] == "v3.5"
    assert result["v3"]["recognized_query_mode"] in {"single", "report"}
    assert result["v3"]["routing_result"] == {"type": "ExecutableQuery", "reason": None}
    assert result["v3"]["v3_5_subroute"] == "mongo"
    assert expected in result["answer"]
    assert "实时行情" not in result["answer"]


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("科创50ETF跟踪什么指数", "fund_identity_ambiguous"),
        ("这只ETF规模多大", "fund_identity_required"),
        ("这只ETF历史走势", "fund_identity_required"),
    ],
)
def test_semantic_query_v3_5_mongo_fallback_preserves_identity_boundaries(question, reason):
    result = semantic_query_v3(question, root=".", dry_run=True, phase="v3.5")

    assert result["v3"]["phase"] == "v3.5"
    assert result["v3"]["v3_5_subroute"] == "mongo"
    assert result["v3"]["routing_result"] == {"type": "UnsupportedQuery", "reason": reason}


def test_semantic_query_v3_4_realtime_denial_is_preserved_in_dry_run():
    result = semantic_query_v3("帮我查510300的实时行情", root=".", dry_run=True, phase="v3.4")

    assert result["v3"]["recognized_query_mode"] == "deny"
    assert result["v3"]["routing_result"]["reason"] == "realtime_not_supported"


def test_execute_realtime_plan_posts_thscodes_and_normalizes_real_payload(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":[{"thscode":"510050.SH","tradeDate":"2026-05-15","tradeTime":"14:59:58","latest":2.5,"change":0.01,"changeRatio":0.004,"open":2.48,"high":2.52,"low":2.47,"amount":123456789,"volume":987654,"latestVolume":100,"sellVolume":2000,"buyVolume":3000,"iopv":2.49,"premium":0.001,"bid1":2.5,"ask1":2.501,"bidSize1":400,"askSize1":500,"swing":0.02}]}'

    def fake_urlopen(req, timeout):
        captured["body"] = req.data
        return Response()

    monkeypatch.setenv("ETF_REALTIME_API_URL", "https://example.test/quote")
    monkeypatch.setattr("etf_agent.realtime_runtime.request.urlopen", fake_urlopen)
    plan = {
        "fundcodes": ["510050"],
        "thscodes": ["510050.SH"],
        "matched_names": {"510050": "上证50ETF"},
        "fields": ["latest", "change", "changeRatio", "amount", "tradeTime"],
        "field_display_matrix": {},
        "source_field_mappings": {},
        "normalization_rules": {},
    }

    result = execute_realtime_plan(plan)

    assert json.loads(captured["body"].decode("utf-8")) == {"codes": ["510050.SH"]}
    assert result["success"] is True
    assert result["source_status"] == "remote"
    assert result["data"] == [
        {
            "fundcode": "510050",
            "thscode": "510050.SH",
            "name": "上证50ETF",
            "latest": 2.5,
            "change": 0.01,
            "changeRatio": 0.004,
            "amount": 123456789,
            "tradeTime": "14:59:58",
        }
    ]


def test_execute_realtime_plan_distinguishes_source_failures(monkeypatch):
    monkeypatch.setenv("ETF_REALTIME_API_URL", "https://example.test/quote")
    plan = {
        "fundcodes": ["510050"],
        "thscodes": ["510050.SH"],
        "matched_names": {},
        "fields": ["latest", "tradeTime"],
        "field_display_matrix": {},
        "source_field_mappings": {},
        "normalization_rules": {},
    }

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":[]}'

    monkeypatch.setattr("etf_agent.realtime_runtime.request.urlopen", lambda req, timeout: EmptyResponse())
    empty = execute_realtime_plan(plan)
    assert empty["success"] is False
    assert empty["source_status"] == "empty"
    assert empty["failure_stage"] == "remote_response_empty"

    class MissingFieldResponse(EmptyResponse):
        def read(self):
            return b'{"data":[{"thscode":"510050.SH","latest":2.5}]}'

    monkeypatch.setattr("etf_agent.realtime_runtime.request.urlopen", lambda req, timeout: MissingFieldResponse())
    missing = execute_realtime_plan(plan)
    assert missing["success"] is False
    assert missing["source_status"] == "missing_fields"
    assert missing["failure_stage"] == "remote_response_missing_fields"
    assert missing["missing_fields"] == {"510050.SH": ["tradeTime"]}
