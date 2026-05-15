from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from etf_agent.ast_validator import validate_v3_3_ast_draft
from etf_agent.formatter import format_answer
from etf_agent.generation_context import build_generation_bundle
from etf_agent.v3 import _apply_timeseries_semantics, _semantic_query_v3_4_strict


def _classification() -> dict:
    return {
        "recognized_query_mode": "single",
        "intent": "fund_scale",
        "intent_candidates": ["fund_scale"],
        "from_candidates": ["tb_ths_etf_base"],
        "entity_hints": {"fundcodes": ["510500"], "period": None},
    }


def _trend_draft(question: str, *, intent: str, field: str, period: str = "1y", count: int | None = None) -> dict:
    spec = {"mode": "series", "period": period}
    if count is not None:
        spec["count"] = count
    return {
        "ast_schema_version": "v3_3_structured_query",
        "intent": intent,
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", field],
        "where": [{"field": "fundcode", "op": "eq", "value": re.search(r"\d{6}", question).group(0)}],
        "order_by": None,
        "limit": 1,
        "output_style": "timeseries_series",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": field, "format": "plain"},
        ],
        "timeseries_semantics": {"by_field": {field: spec}},
        "report_period": None,
        "expand": None,
    }


def test_v3_4_nav_trend_uses_ast_path_and_outputs_series(monkeypatch):
    seen = {}

    def fake_generate_full_ast_draft_with_llm(**kwargs):
        seen["phase"] = kwargs["generation_context"]["llm_context"]["phase"]
        seen["timeseries_contract"] = kwargs["generation_context"]["llm_context"]["timeseries_contract"]
        draft = _trend_draft(
            kwargs["question"],
            intent="nav_trend",
            field="ths_unit_nv_fund",
            period="business_days",
            count=5,
        )
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft, "usage": {"total_tokens": 0}}

    def fake_execute_v3_plan(plan, config_obj, *, dry_run, no_llm):
        seen["plan"] = plan
        return {
            "success": True,
            "data": {
                "fundcode": "510500",
                "ths_fund_extended_inner_short_name_fund": "中证500ETF",
                "ths_unit_nv_fund": [
                    {"btime": "2026-05-09", "value": 8.7},
                    {"btime": "2026-05-07", "value": 8.5},
                    {"btime": "2026-05-11", "value": 8.9},
                    {"btime": "2026-05-06", "value": 8.4},
                    {"btime": "2026-05-08", "value": 8.6},
                    {"btime": "2026-05-10", "value": 8.8},
                ],
            },
        }

    monkeypatch.setattr("etf_agent.v3.generate_full_ast_draft_with_llm", fake_generate_full_ast_draft_with_llm)
    monkeypatch.setattr("etf_agent.v3._execute_v3_plan", fake_execute_v3_plan)

    result = _semantic_query_v3_4_strict(
        "510500 近5日净值走势",
        config_obj=SimpleNamespace(),
        classification=_classification(),
    )

    assert seen["phase"] == "v3.4"
    assert seen["timeseries_contract"]["ths_unit_nv_fund"] == {"mode": "series", "period": "business_days", "count": 5}
    assert result["v3"]["phase"] == "v3.4"
    assert result["v3"]["intent"] == "nav_trend"
    assert result["query_plan"]["output_style"] == "timeseries_series"
    assert result["query_plan"]["timeseries_semantics"]["by_field"]["ths_unit_nv_fund"]["count"] == 5
    data = result["result"]["data"]
    assert isinstance(data, dict)
    series = data["series"]
    assert len(series) == 1
    assert series[0]["field"] == "ths_unit_nv_fund"
    assert series[0]["period"] == "business_days"
    assert series[0]["count"] == 5
    assert [point["btime"] for point in series[0]["points"]] == [
        "2026-05-07",
        "2026-05-08",
        "2026-05-09",
        "2026-05-10",
        "2026-05-11",
    ]
    assert "部分数据点" in result["answer"]
    assert "中证500ETF（510500）近5个交易日单位净值走势已查询到，共 5 个数据点，覆盖 2026-05-07 至 2026-05-11。" in result["answer"]
    assert len(re.findall(r"\d{4}-\d{2}-\d{2}[：:]", result["answer"])) == 5
    assert "2026-05-07：8.5" in result["answer"]
    assert "2026-05-11：8.9" in result["answer"]
    assert not re.search(r"[+-]\d+(?:\.\d+)?%", result["answer"])


def test_v3_4_scale_share_generation_context_selects_requested_series_fields():
    scale_bundle = build_generation_bundle(
        "510500 近一年规模变化",
        query_mode="single",
        intent="scale_share_trend",
        entity_hints={"fundcodes": ["510500"], "period": "1y"},
        phase="v3.4",
    )
    share_bundle = build_generation_bundle(
        "159919 份额变化趋势",
        query_mode="single",
        intent="scale_share_trend",
        entity_hints={"fundcodes": ["159919"], "period": "1y"},
        phase="v3.4",
    )
    both_bundle = build_generation_bundle(
        "510500 规模和份额走势",
        query_mode="single",
        intent="scale_share_trend",
        entity_hints={"fundcodes": ["510500"], "period": "1y"},
        phase="v3.4",
    )

    assert scale_bundle["validator_expectations"]["required_select_fields"] == ["ths_fund_scale_fund"]
    assert share_bundle["validator_expectations"]["required_select_fields"] == ["ths_fund_shares_fund"]
    assert both_bundle["validator_expectations"]["required_select_fields"] == [
        "ths_fund_scale_fund",
        "ths_fund_shares_fund",
    ]
    assert scale_bundle["validator_expectations"]["expected_timeseries_modes"]["ths_fund_scale_fund"] == {
        "mode": "series",
        "period": "1y",
    }


def test_v3_4_scale_and_share_trend_outputs_two_raw_value_series(monkeypatch):
    def fake_generate_full_ast_draft_with_llm(**kwargs):
        context = kwargs["generation_context"]
        expected = context["validator_expectations"]["expected_timeseries_modes"]
        fields = context["validator_expectations"]["required_select_fields"]
        draft = {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "scale_share_trend",
            "sub_intents": [],
            "from": "tb_ths_etf_base",
            "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", *fields],
            "where": [{"field": "fundcode", "op": "eq", "value": "510500"}],
            "order_by": None,
            "limit": 1,
            "output_style": "timeseries_series",
            "answer_fields": [{"field": field, "format": "plain"} for field in ["fundcode", "ths_fund_extended_inner_short_name_fund", *fields]],
            "timeseries_semantics": {"by_field": expected},
            "report_period": None,
            "expand": None,
        }
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft, "usage": {"total_tokens": 0}}

    monkeypatch.setattr("etf_agent.v3.generate_full_ast_draft_with_llm", fake_generate_full_ast_draft_with_llm)
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510500",
                "ths_fund_extended_inner_short_name_fund": "中证500ETF",
                "ths_fund_scale_fund": [{"btime": "2026-05-11", "value": 12300000000}],
                "ths_fund_shares_fund": [{"btime": "2026-05-11", "value": 4560000000}],
            },
        },
    )

    result = _semantic_query_v3_4_strict("510500 规模和份额走势", config_obj=SimpleNamespace(), classification=_classification())

    series = result["result"]["data"]["series"]
    assert [item["field"] for item in series] == ["ths_fund_scale_fund", "ths_fund_shares_fund"]
    assert [item["format"] for item in series] == ["yuan_to_100m", "shares_to_100m"]
    assert series[0]["points"][0]["value"] == 12300000000
    assert series[1]["points"][0]["value"] == 4560000000
    assert "中证500ETF（510500）近一年基金规模、基金份额走势已查询到，共 2 个数据点，覆盖 2026-05-11 至 2026-05-11。" in result["answer"]
    assert "基金规模：2026-05-11：123.00 亿元" in result["answer"]
    assert "基金份额：2026-05-11：45.60亿份" in result["answer"]
    assert "上涨" not in result["answer"]


def test_v3_4_validator_applies_expected_series_defaults_when_llm_omits_timeseries():
    bundle = build_generation_bundle(
        "510500 近一年净值走势",
        query_mode="single",
        intent="nav_trend",
        entity_hints={"fundcodes": ["510500"], "period": "1y"},
        phase="v3.4",
    )
    draft = _trend_draft("510500 近一年净值走势", intent="nav_trend", field="ths_unit_nv_fund")
    draft["timeseries_semantics"] = None

    validation = validate_v3_3_ast_draft(draft, query_mode="single", intent="nav_trend", generation_bundle=bundle)

    assert validation["validated_ast"]["timeseries_semantics"]["by_field"]["ths_unit_nv_fund"] == {
        "mode": "series",
        "period": "1y",
    }
    assert validation["validator_applied_defaults"]["timeseries_semantics"]["ths_unit_nv_fund"]["mode"] == "series"


def test_apply_timeseries_semantics_series_keeps_raw_scale_values_and_formats_answer():
    ast = {
        "timeseries_semantics": {
            "by_field": {
                "ths_fund_scale_fund": {"mode": "series", "period": "3m"},
                "ths_fund_shares_fund": {"mode": "series", "period": "3m"},
            }
        }
    }
    result = {
        "success": True,
        "data": {
            "fundcode": "510500",
            "ths_fund_extended_inner_short_name_fund": "中证500ETF",
            "ths_fund_scale_fund": [
                {"btime": "2026-01-01", "value": 10000000000},
                {"btime": "2026-05-01", "value": 12300000000},
            ],
            "ths_fund_shares_fund": [
                {"btime": "2026-05-01", "value": 4560000000},
            ],
        },
    }

    trimmed = _apply_timeseries_semantics(ast, result)
    plan = {
        "output_style": "timeseries_series",
        "timeseries_semantics": ast["timeseries_semantics"],
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "yuan_to_100m"},
            {"field": "ths_fund_shares_fund", "label": "基金份额", "format": "shares_to_100m"},
        ],
    }
    answer = format_answer(plan, trimmed)

    series = trimmed["data"]["series"]
    assert {item["field"]: item["format"] for item in series} == {
        "ths_fund_scale_fund": "yuan_to_100m",
        "ths_fund_shares_fund": "shares_to_100m",
    }
    assert series[0]["points"][0]["value"] == 12300000000
    assert "共 2 个数据点" in answer
    assert "中证500ETF（510500）近三个月基金规模、基金份额走势已查询到，共 2 个数据点，覆盖 2026-05-01 至 2026-05-01。" in answer
    assert "部分数据点" in answer
    assert "基金规模：2026-05-01：123.00 亿元" in answer
    assert "基金份额：2026-05-01：45.60亿份" in answer
    assert "上涨" not in answer
    assert "变动率" not in answer


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("510500 近99999个交易日净值走势", "period_window_too_large"),
        ("510500 净值变了多少", "derived_not_supported"),
        ("510500 规模变动率是多少", "derived_not_supported"),
        ("510500 净现金流走势", "series_not_enabled"),
    ],
)
def test_v3_4_unsupported_reasons_are_structured(question, reason):
    result = _semantic_query_v3_4_strict(question, config_obj=SimpleNamespace(), classification=_classification())

    assert result["v3"]["phase"] == "v3.4"
    assert result["v3"]["failure_reason"] == reason
    assert result["v3"]["routing_result"] == {"type": "UnsupportedQuery", "reason": reason}
