from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from etf_agent.ast_generator import generate_full_ast_draft_with_llm
from etf_agent.ast_validator import validate_v3_3_ast_draft
from etf_agent.formatter import format_answer
from etf_agent.generation_context import build_generation_bundle
from etf_agent.v3 import _compile_ast_to_plan, build_v3_1_ast, extract_v3_1_entity_hints, semantic_query_v3


ROOT = Path(__file__).resolve().parents[1]


def _answer_body(answer: str) -> str:
    for marker in ("\n\n数据起始日：", "\n\n数据结束日：", "\n\n数据起止日：", "\n\n数据日期："):
        if marker in str(answer):
            return str(answer).split(marker, 1)[0]
    return str(answer)


def _derived_draft(**overrides):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "grammar_fragment_id": "derived_performance",
        "compiler_rule_id": "derived_performance_table",
        "profile": "derived_performance_table",
        "intent": "performance",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            {"alias": "return_1y", "type": "derived_return", "period": "1y"},
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "performance_table",
        "answer_fields": [{"field": "fundcode", "format": "plain"}],
        "performance_rows": [{"alias": "return_1y", "period": "1y", "label": "近1年收益率"}],
        "report_period": None,
        "expand": None,
    }
    draft.update(overrides)
    return draft


def _base_v3_2_draft(**overrides):
    draft = {
        "ast_schema_version": "v3_2_base_ast",
        "intent": "basic_info",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_name_of_tracking_index_fund",
            "ths_fund_scale_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_name_of_tracking_index_fund", "format": "plain"},
            {"field": "ths_fund_scale_fund", "format": "amount"},
        ],
        "report_period": None,
        "expand": None,
    }
    draft.update(overrides)
    return draft


def test_v3_3_generation_bundle_exposes_protocol_schema_and_fragment_metadata():
    bundle = build_generation_bundle(
        "510300按净值序列重新计算近一年收益率是多少",
        query_mode="single",
        intent="performance",
        entity_hints={"fundcodes": ["510300"], "period": "1y"},
        phase="v3.3",
    )

    contract = bundle["llm_context"]["strict_validation_contract"]

    assert bundle["llm_context"]["ast_schema_version"] == "v3_3_structured_query"
    assert bundle["llm_context"]["grammar_fragment_id"] == "derived_performance"
    assert contract["allowed_profiles"] == ["derived_performance_table"]
    assert contract["required_derived_aliases"] == ["return_1y"]
    assert contract["required_performance_rows"] == ["return_1y"]


def test_v3_3_generation_bundle_orders_composite_single_scale_fee_performance_contract():
    bundle = build_generation_bundle(
        "帮我看看510500的规模大不大，费率贵不贵，收益好不好",
        query_mode="single",
        intent="composite_single",
        entity_hints={"fundcodes": ["510500"], "period": "std"},
        phase="v3.3",
    )

    contract = bundle["llm_context"]["strict_validation_contract"]

    assert contract["required_select_fields"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_yeild_std_fund",
    ]
    assert contract["required_answer_fields"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_yeild_std_fund",
    ]
    assert "derived_performance_contract" not in bundle["llm_context"]
    assert contract["expected_sub_intents"] == ["fund_scale", "fee", "performance"]


def test_v3_3_generation_bundle_keeps_standard_performance_on_remote_yield_fields():
    bundle = build_generation_bundle(
        "159919近1年收益，同类排名第几",
        query_mode="single",
        intent="performance",
        entity_hints={"fundcodes": ["159919"], "period": "1y"},
        phase="v3.3",
    )

    contract = bundle["llm_context"]["strict_validation_contract"]
    selection_context = bundle["selection_context"]

    assert "derived_performance_contract" not in bundle["llm_context"]
    assert contract["required_select_fields"] == [
        "ths_yeild_1y_fund",
        "ths_yeild_rank_1y_fund_origin",
    ]
    assert contract["required_answer_fields"] == [
        "ths_yeild_1y_fund",
        "ths_yeild_rank_1y_fund_origin",
    ]
    assert "ths_unit_nv_fund" not in selection_context["selectable_fields"]
    assert "return_1y" not in contract["required_select_fields"]


def test_v3_3_report_holding_contract_requires_stock_code_with_net_value_ratio():
    bundle = build_generation_bundle(
        "510300前十大重仓股占净值比多少",
        query_mode="report",
        intent="report_holding",
        entity_hints={"fundcodes": ["510300"], "period": "1y", "report_period": {"mode": "latest"}},
        phase="v3.3",
    )

    contract = bundle["llm_context"]["strict_validation_contract"]

    assert "ths_top_held_stock_code_fund" in contract["required_select_fields"]
    assert "ths_top_stock_mv_to_fnv_fund" in contract["required_select_fields"]
    assert "ths_top_held_stock_code_fund" in contract["required_answer_fields"]
    assert "ths_top_stock_mv_to_fnv_fund" in contract["required_answer_fields"]


def test_v3_3_fund_share_formatter_uses_100m_share_units_for_latest_two_change():
    plan = {
        "filter": {"fundcode": "510300"},
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_shares_fund", "label": "基金份额", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "fundcode": "510300",
            "ths_fund_shares_fund": {
                "current": {"value": 35270000000.0, "btime": "2026-05-10"},
                "previous": {"value": 35270000000.0, "btime": "2026-05-09"},
                "delta": 0.0,
                "delta_pct": 0.0,
                "direction": "flat",
            },
        },
    }

    answer = format_answer(plan, result)

    assert "352.70亿份" in answer
    assert "较前一期" in answer
    assert "持平" in answer
    assert "3.527e+10" not in answer


def test_v3_3_fund_share_formatter_uses_100m_share_units_for_latest_snapshot():
    plan = {
        "filter": {"fundcode": "510300"},
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_shares_fund", "label": "基金份额", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "fundcode": "510300",
            "ths_fund_shares_fund": 35270000000.0,
        },
    }

    answer = format_answer(plan, result)

    assert "352.70亿份" in answer
    assert "3.527e+10" not in answer


def test_v3_3_performance_formatter_shows_yield_and_rank_together():
    plan = {
        "filter": {"fundcode": "159919"},
        "output_style": "performance_table",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_yeild_1y_fund", "label": "近1年收益率", "format": "percent"},
            {"field": "ths_yeild_rank_1y_fund_origin", "label": "近1年同类排名", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "fundcode": "159919",
            "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
            "ths_yeild_1y_fund": 10.23,
            "ths_yeild_rank_1y_fund_origin": "7362/22995",
        },
    }

    answer = format_answer(plan, result)

    assert "10.23%" in answer
    assert "7362/22995" in answer
    assert "收益率为 10.23%" in answer or "收益率为10.23%" in answer
    assert "rank_num" not in answer


def test_v3_3_manager_detail_formatter_summarizes_manager_array_without_raw_json():
    plan = {
        "filter": {"fundcode": "510300"},
        "output_style": "manager_detail",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_fund_manager_current_fund", "label": "基金经理(现任)", "format": "plain"},
            {"field": "ths_manager", "label": "基金经理详情", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "fundcode": "510300",
            "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
            "ths_fund_manager_current_fund": "柳军",
            "ths_manager": [
                {
                    "ths_service_sd_fund": "2012-05-04",
                    "ths_service_duration_annual_return_fund": "6.05",
                    "ths_rzjjzgm_fund": "338801000000",
                    "ths_tenure_fund": "5121",
                    "ths_name_fund": "柳军",
                    "rank_num": 1,
                }
            ],
        },
    }

    answer = format_answer(plan, result)

    assert "现任基金经理柳军" in answer
    assert "自2012-05-04起任职" in answer
    assert "5121天" in answer
    assert "6.05%" in answer
    assert "3388.01亿元" in answer
    assert "[{" not in answer
    assert "ths_" not in answer


def test_v3_3_filter_yield_sort_without_explicit_period_defaults_to_ytd():
    question = "筛选跟踪沪深300指数的ETF，按收益率排序"
    hints = extract_v3_1_entity_hints(question)
    ast = build_v3_1_ast("filter", hints, question)

    assert hints["order_by"] == {"field": "ths_yeild_ytd_fund", "direction": "desc"}
    assert ast["order_by"] == {"field": "ths_yeild_ytd_fund", "direction": "desc"}
    assert any(item["field"] == "ths_yeild_ytd_fund" and item["format"] == "percent" for item in ast["answer_fields"])


@pytest.mark.parametrize(
    "question",
    [
        "哪些ETF管理费率最低",
        "管理费率低于0.2%的ETF有哪些",
    ],
)
def test_v3_3_fee_filter_sorts_by_fee_then_scale_then_fundcode(question):
    hints = extract_v3_1_entity_hints(question)
    ast = build_v3_1_ast("filter", hints, question)
    plan = _compile_ast_to_plan(ast)

    assert ast["order_by"] == {"field": "ths_manage_fee_rate_fund", "direction": "asc"}
    assert plan["sort"] == [
        ["ths_manage_fee_rate_fund", 1],
        ["ths_fund_scale_fund", -1],
        ["fundcode", 1],
    ]
    if "低于0.2%" in question:
        assert plan["filter"]["ths_manage_fee_rate_fund"] == {"$lt": 0.2}


@pytest.mark.parametrize(
    ("question", "field", "expected_filter"),
    [
        ("今年以来收益排名前10的ETF", "ths_yeild_ytd_fund", None),
        ("近1年收益率超过20%的ETF", "ths_yeild_1y_fund", {"$gt": 20.0}),
    ],
)
def test_v3_3_yield_filter_lists_use_remote_authoritative_yield_fields(question, field, expected_filter):
    hints = extract_v3_1_entity_hints(question)
    ast = build_v3_1_ast("filter", hints, question)
    plan = _compile_ast_to_plan(ast)

    assert ast["order_by"]["field"] == field
    assert field in ast["select"]
    assert field in [item["field"] for item in ast["answer_fields"]]
    assert "ths_unit_nv_fund" not in ast["select"]
    if expected_filter is not None:
        assert plan["filter"][field] == expected_filter


def test_v3_3_filter_without_return_semantics_does_not_require_derived_contract():
    bundle = build_generation_bundle(
        "帮我找跟踪沪深300指数、费率最低的ETF，然后看它的基本信息和收益",
        query_mode="filter",
        intent="filter",
        entity_hints={
            "fundcodes": [],
            "filters": [
                {
                    "field": "ths_name_of_tracking_index_fund",
                    "op": "eq",
                    "value": "沪深300指数",
                }
            ],
            "order_by": {"field": "ths_manage_fee_rate_fund", "direction": "asc"},
            "limit_hint": 1,
            "period": "1y",
        },
        phase="v3.3",
    )

    assert "derived_performance_contract" not in bundle["llm_context"]
    assert "v3_3" not in bundle["validator_expectations"]


def test_v3_3_validator_accepts_v3_2_base_ast_subset():
    bundle = build_generation_bundle(
        "510300是什么",
        query_mode="single",
        intent="basic_info",
        entity_hints={"fundcodes": ["510300"]},
        phase="v3.3",
    )
    draft = _base_v3_2_draft()

    validated = validate_v3_3_ast_draft(
        draft,
        query_mode="single",
        intent="basic_info",
        generation_bundle=bundle,
    )

    assert validated["validated_ast"]["ast_schema_version"] == "v3_2_base_ast"
    assert "performance_rows" not in validated["validated_ast"]


def test_v3_3_semantic_query_executes_v3_2_base_ast_subset(monkeypatch):
    draft = _base_v3_2_draft()

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                "ths_name_of_tracking_index_fund": "沪深300指数",
                "ths_fund_scale_fund": 1000000000,
            },
        },
    )

    result = semantic_query_v3("510300是什么", root=ROOT)

    assert result["v3"]["ast_schema_version"] == "v3_2_base_ast"
    assert result["query_plan"]["collection"] == "tb_ths_etf_base"
    assert result["result"]["success"] is True
    assert "510300" in result["answer"]


def test_v3_3_semantic_query_executes_report_scalar_ast(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "institution_holding",
        "sub_intents": [],
        "from": "tb_ths_etf_report_year",
        "select": [
            "fundcode",
            "thscode",
            "year_num",
            "type_num",
            "ths_org_investor_total_held_ratio_fund",
            "ths_org_investor_total_held_shares_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "thscode", "format": "plain"},
            {"field": "year_num", "format": "plain"},
            {"field": "type_num", "format": "plain"},
            {"field": "ths_org_investor_total_held_ratio_fund", "format": "percent"},
            {"field": "ths_org_investor_total_held_shares_fund", "format": "plain"},
        ],
        "report_period": {"mode": "latest"},
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "thscode": "510300.SH",
                "year_num": 2025,
                "type_num": 4,
                "ths_org_investor_total_held_ratio_fund": 12.5,
                "ths_org_investor_total_held_shares_fund": 345678901,
            },
        },
    )

    result = semantic_query_v3("510300的机构持有比例是多少", root=ROOT)

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["query_plan"]["collection"] == "tb_ths_etf_report_year"
    assert result["result"]["success"] is True
    assert "机构投资者持有比例" in result["answer"]


def test_v3_3_semantic_query_executes_report_array_ast(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "report_holding",
        "sub_intents": [],
        "from": "tb_ths_etf_report_year",
        "select": [
            "fundcode",
            "thscode",
            "year_num",
            "type_num",
            "ths_top_held_stock_code_fund",
            "ths_top_stock_mv_to_fnv_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "report_list",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "thscode", "format": "plain"},
            {"field": "year_num", "format": "plain"},
            {"field": "type_num", "format": "plain"},
            {"field": "ths_top_held_stock_code_fund", "format": "plain"},
            {"field": "ths_top_stock_mv_to_fnv_fund", "format": "percent"},
        ],
        "report_period": {"mode": "latest"},
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "thscode": "510300.SH",
                "year_num": 2025,
                "type_num": 4,
                "ths_top_held_stock_code_fund": [
                    {"rank_num": 1, "value": "600000.SH"},
                    {"rank_num": 2, "value": "600001.SH"},
                ],
                "ths_top_stock_mv_to_fnv_fund": [
                    {"rank_num": 1, "value": 12.3},
                    {"rank_num": 2, "value": 10.1},
                ],
            },
        },
    )

    result = semantic_query_v3("510300前十大重仓股是什么", root=ROOT)

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["query_plan"]["collection"] == "tb_ths_etf_report_year"
    assert result["result"]["success"] is True
    assert "排名" in result["answer"]
    assert "600000.SH" in result["answer"]
    assert "12.30%" in result["answer"]


def test_v3_3_report_validator_adds_period_context_without_semantic_repair():
    bundle = build_generation_bundle(
        "510300前十大重仓股是什么",
        query_mode="report",
        intent="report_holding",
        entity_hints={"fundcodes": ["510300"], "period": "1y", "report_period": {"mode": "latest"}},
        phase="v3.3",
    )
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "report_holding",
        "sub_intents": [],
        "from": "tb_ths_etf_report_year",
        "select": [
            "ths_top_held_stock_code_fund",
            "ths_top_stock_mv_to_fnv_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "report_list",
        "answer_fields": [
            {"field": "ths_top_held_stock_code_fund", "format": "plain"},
            {"field": "ths_top_stock_mv_to_fnv_fund", "format": "percent"},
        ],
        "timeseries_semantics": None,
        "report_period": {"mode": "latest"},
        "expand": None,
    }

    validation = validate_v3_3_ast_draft(
        draft,
        query_mode="report",
        intent="report_holding",
        generation_bundle=bundle,
    )

    validated = validation["validated_ast"]
    assert "year_num" in validated["select"]
    assert "type_num" in validated["select"]
    assert validation["provenance_diff"]["validator_additions_by_kind"]["identity"] == ["fundcode"]
    assert validation["provenance_diff"]["validator_additions_by_kind"]["context"] == [
        "year_num",
        "type_num",
    ]
    assert validation["provenance_diff"]["strict_pass"] is True


def test_v3_3_report_formatter_uses_report_period_context_without_raw_fields():
    list_plan = {
        "filter": {"fundcode": "510300"},
        "output_style": "report_list",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "year_num", "label": "年份", "format": "plain"},
            {"field": "type_num", "label": "报告期类型", "format": "plain"},
            {"field": "ths_top_held_stock_code_fund", "label": "前十大重仓股代码", "format": "plain"},
        ],
    }
    list_result = {
        "success": True,
        "data": {
            "fundcode": "510300",
            "year_num": 2024,
            "type_num": 4,
            "ths_top_held_stock_code_fund": [{"rank_num": 1, "value": "600519"}],
        },
    }
    summary_plan = {
        "filter": {"fundcode": "510300"},
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "year_num", "label": "年份", "format": "plain"},
            {"field": "type_num", "label": "报告期类型", "format": "plain"},
            {"field": "ths_org_investor_total_held_ratio_fund", "label": "机构投资者持有比例", "format": "percent"},
        ],
    }
    summary_result = {
        "success": True,
        "data": {
            "fundcode": "510300",
            "year_num": 2024,
            "type_num": 4,
            "ths_org_investor_total_held_ratio_fund": 83.68,
        },
    }

    list_answer = format_answer(list_plan, list_result)
    summary_answer = format_answer(summary_plan, summary_result)

    assert "2024年年报" in list_answer
    assert "2024年年报" in summary_answer
    assert "年份为" not in summary_answer
    assert "报告期类型为" not in summary_answer


def test_v3_3_report_formatter_treats_type_num_6_as_year_report():
    plan = {
        "filter": {"fundcode": "510300"},
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_invest_style_fund", "label": "投资风格", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "fundcode": "510300",
            "year_num": 2024,
            "type_num": 6,
            "ths_invest_style_fund": "平衡型基金",
        },
    }

    answer = format_answer(plan, result)

    assert "2024年年报" in answer
    assert "平衡型基金" in answer


def test_v3_3_semantic_query_executes_manager_detail_ast(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "manager_detail",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "manager_detail",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_fund_manager_current_fund", "format": "plain"},
            {"field": "ths_fund_supervisor_fund", "format": "plain"},
        ],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                "ths_fund_manager_current_fund": "张三",
                "ths_fund_supervisor_fund": "某基金公司",
            },
        },
    )

    result = semantic_query_v3("510300现任基金经理管理了多久", root=ROOT)

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["query_plan"]["collection"] == "tb_ths_etf_base"
    assert result["result"]["success"] is True
    assert "基金经理" in result["answer"]


def test_v3_3_semantic_query_executes_trading_metric_ast(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "trading_metric",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_amt_fund",
            "ths_netcashflow_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "trading_metric",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_amt_fund", "format": "amount"},
            {"field": "ths_netcashflow_fund", "format": "amount"},
        ],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                "ths_amt_fund": 123456789,
                "ths_netcashflow_fund": -9876543,
            },
        },
    )

    result = semantic_query_v3("510300最近成交额多少", root=ROOT)

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["query_plan"]["collection"] == "tb_ths_etf_base"
    assert result["result"]["success"] is True
    assert "成交额" in result["answer"]


def test_v3_3_semantic_query_executes_fund_share_latest_two_timeseries(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "fund_scale",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_shares_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_shares_fund", "format": "plain"},
        ],
        "timeseries_semantics": {
            "by_field": {
                "ths_fund_shares_fund": {"mode": "latest_two"},
            }
        },
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_fund_shares_fund": [
                    {"value": 1000000000, "btime": "2026-03-31"},
                    {"value": 1250000000, "btime": "2026-05-05"},
                ],
            },
        },
    )

    result = semantic_query_v3("510300的基金份额最近有变化吗", root=ROOT, dry_run=False, no_llm=False, phase="v3.3")

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["v3"]["recognized_query_mode"] == "single"
    assert result["result"]["success"] is True
    assert "增加" in result["answer"] or "减少" in result["answer"]
    assert "2026-05-05" in result["answer"]


def test_v3_3_semantic_query_executes_composite_single_scale_fee_performance(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "composite_single",
        "sub_intents": ["fund_scale", "fee", "performance"],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_scale_fund",
            "ths_manage_fee_rate_fund",
            "ths_yeild_std_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510500"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_fund_scale_fund", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "format": "percent"},
            {"field": "ths_yeild_std_fund", "label": "成立以来收益率", "format": "percent"},
        ],
        "timeseries_semantics": None,
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "510500",
                "ths_fund_extended_inner_short_name_fund": "中证500ETF",
                "ths_fund_scale_fund": 180000000000,
                "ths_manage_fee_rate_fund": 0.15,
                "ths_yeild_std_fund": 24.50,
            },
        },
    )

    result = semantic_query_v3("帮我看看510500的规模大不大，费率贵不贵，收益好不好", root=ROOT, dry_run=False, no_llm=False, phase="v3.3")

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["v3"]["grammar_fragment_id"] is None
    assert result["v3"]["compiler_rule_id"] is None
    assert result["v3"]["recognized_query_mode"] == "single"
    assert result["v3"]["intent"] == "composite_single"
    assert result["result"]["success"] is True
    assert "ths_unit_nv_fund" in result["query_plan"]["projection"]
    assert "ths_yeild_std_fund" in result["query_plan"]["projection"]
    assert "规模" in result["answer"]
    assert "费率" in result["answer"]
    assert "收益" in result["answer"]
    assert "24.50%" in result["answer"]


def test_v3_3_semantic_query_executes_cross_collection_composite_bundle(monkeypatch):
    question = "510300今年收益多少，持仓了哪些行业，基金经理是谁"

    drafts = {
        ("single", "performance"): {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "performance",
            "sub_intents": [],
            "from": "tb_ths_etf_base",
            "select": [
                "fundcode",
                "ths_fund_extended_inner_short_name_fund",
                "ths_yeild_ytd_fund",
            ],
            "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
            "order_by": None,
            "limit": 1,
            "output_style": "performance_table",
            "answer_fields": [
                {"field": "fundcode", "format": "plain"},
                {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
                {"field": "ths_yeild_ytd_fund", "format": "percent"},
            ],
            "timeseries_semantics": None,
            "report_period": None,
            "expand": None,
        },
        ("report", "report_industry"): {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "report_industry",
            "sub_intents": [],
            "from": "tb_ths_etf_report_year",
            "select": [
                "fundcode",
                "year_num",
                "type_num",
                "ths_top_n_top_industry_name_fund",
                "ths_top_n_top_industry_mv_to_equity_fund",
            ],
            "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
            "order_by": None,
            "limit": 1,
            "output_style": "report_list",
            "answer_fields": [
                {"field": "fundcode", "format": "plain"},
                {"field": "year_num", "format": "plain"},
                {"field": "type_num", "format": "plain"},
                {"field": "ths_top_n_top_industry_name_fund", "format": "plain"},
                {"field": "ths_top_n_top_industry_mv_to_equity_fund", "format": "percent"},
            ],
            "timeseries_semantics": None,
            "report_period": {"mode": "latest"},
            "expand": None,
        },
        ("single", "manager_detail"): {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "manager_detail",
            "sub_intents": [],
            "from": "tb_ths_etf_base",
            "select": [
                "fundcode",
                "ths_fund_extended_inner_short_name_fund",
                "ths_fund_manager_current_fund",
                "ths_fund_supervisor_fund",
            ],
            "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
            "order_by": None,
            "limit": 1,
            "output_style": "manager_detail",
            "answer_fields": [
                {"field": "fundcode", "format": "plain"},
                {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
                {"field": "ths_fund_manager_current_fund", "format": "plain"},
                {"field": "ths_fund_supervisor_fund", "format": "plain"},
            ],
            "timeseries_semantics": None,
            "report_period": None,
            "expand": None,
        },
    }

    def fake_generate_full_ast_draft_with_llm(**kwargs):
        capability = kwargs["generation_context"]["llm_context"]["capability"]
        key = (capability["recognized_query_mode"], capability["intent"])
        if key == ("single", "composite_single"):
            raise AssertionError("cross-collection composite must run child ASTs, not a single parent AST")
        draft = drafts[key]
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft}

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        fake_generate_full_ast_draft_with_llm,
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_mongo_phase",
        lambda mongo_phase, config_obj: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_unit_nv_fund": [
                    {"btime": "2026-01-02", "value": 1.0},
                    {"btime": "2026-05-10", "value": 1.08},
                ],
            },
        },
    )

    def fake_execute_v3_plan(plan, config_obj, *, dry_run, no_llm):
        if plan["collection"] == "tb_ths_etf_report_year":
            return {
                "success": True,
                "data": {
                    "fundcode": "510300",
                    "year_num": 2024,
                    "type_num": 4,
                    "ths_top_n_top_industry_name_fund": [
                        {"rank_num": 1, "value": "银行"},
                    ],
                    "ths_top_n_top_industry_mv_to_equity_fund": [
                        {"rank_num": 1, "value": 24.59},
                    ],
                },
            }
        if "ths_yeild_ytd_fund" in plan.get("projection", []):
            return {
                "success": True,
                "data": {
                    "fundcode": "510300",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_ytd_fund": 5.50,
                },
            }
        return {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                "ths_fund_manager_current_fund": "柳军",
                "ths_fund_supervisor_fund": "华泰柏瑞基金",
            },
        }

    monkeypatch.setattr("etf_agent.v3._execute_v3_plan", fake_execute_v3_plan)

    result = semantic_query_v3(question, root=ROOT, dry_run=False, no_llm=False, phase="v3.3")

    assert result["failure_stage"] is None
    assert result["v3"]["recognized_query_mode"] == "composite"
    assert result["v3"]["intent"] == "composite_single"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["v3_ast"]["intent"] == "composite_single"
    assert len(result["v3_ast"]["steps"]) == 3
    assert len(result["query_plan"]["steps"]) == 3
    assert result["result"]["success"] is True
    assert "今年以来收益率" in result["answer"]
    assert "银行" in result["answer"]
    assert "柳军" in result["answer"]


def test_v3_3_semantic_query_executes_search_two_step_composite_with_name_fallback(monkeypatch):
    question = "搜索中证红利，查一下它的基本信息和持仓"

    drafts = {
        ("search", "search"): {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "search",
            "sub_intents": [],
            "from": "tb_ths_etf_base",
            "select": [
                "fundcode",
                "ths_fund_extended_inner_short_name_fund",
                "ths_fund_scale_fund",
            ],
            "where": [{"field": "__search_text__", "op": "contains", "value": "中证红利"}],
            "order_by": None,
            "limit": 20,
            "output_style": "list",
            "answer_fields": [
                {"field": "fundcode", "format": "plain"},
                {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
                {"field": "ths_fund_scale_fund", "format": "amount"},
            ],
            "report_period": None,
            "expand": None,
        },
        ("single", "basic_info"): {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "basic_info",
            "sub_intents": [],
            "from": "tb_ths_etf_base",
            "select": [
                "fundcode",
                "ths_fund_extended_inner_short_name_fund",
                "ths_name_of_tracking_index_fund",
                "ths_fund_scale_fund",
            ],
            "where": [{"field": "fundcode", "op": "eq", "value": "510880"}],
            "order_by": None,
            "limit": 1,
            "output_style": "summary",
            "answer_fields": [
                {"field": "fundcode", "format": "plain"},
                {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
                {"field": "ths_name_of_tracking_index_fund", "format": "plain"},
                {"field": "ths_fund_scale_fund", "format": "amount"},
            ],
            "timeseries_semantics": None,
            "report_period": None,
            "expand": None,
        },
        ("report", "report_industry"): {
            "ast_schema_version": "v3_3_structured_query",
            "intent": "report_industry",
            "sub_intents": [],
            "from": "tb_ths_etf_report_year",
            "select": [
                "fundcode",
                "year_num",
                "type_num",
                "ths_top_n_top_industry_name_fund",
                "ths_top_n_top_industry_mv_to_equity_fund",
            ],
            "where": [{"field": "fundcode", "op": "eq", "value": "510880"}],
            "order_by": None,
            "limit": 1,
            "output_style": "report_list",
            "answer_fields": [
                {"field": "fundcode", "format": "plain"},
                {"field": "year_num", "format": "plain"},
                {"field": "type_num", "format": "plain"},
                {"field": "ths_top_n_top_industry_name_fund", "format": "plain"},
                {"field": "ths_top_n_top_industry_mv_to_equity_fund", "format": "percent"},
            ],
            "timeseries_semantics": None,
            "report_period": {"mode": "latest"},
            "expand": None,
        },
    }

    def fake_generate_full_ast_draft_with_llm(**kwargs):
        capability = kwargs["generation_context"]["llm_context"]["capability"]
        key = (capability["recognized_query_mode"], capability["intent"])
        draft = drafts[key]
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft}

    monkeypatch.setattr("etf_agent.v3.generate_full_ast_draft_with_llm", fake_generate_full_ast_draft_with_llm)
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": [] if plan["collection"] == "tb_ths_etf_base" and plan["output_style"] == "list" else {
                "fundcode": "510880",
                "ths_fund_extended_inner_short_name_fund": "中证红利ETF",
                "ths_fund_scale_fund": 9876543210,
                "year_num": 2024,
                "type_num": 4,
                "ths_top_n_top_industry_name_fund": [{"rank_num": 1, "value": "银行"}],
                "ths_top_n_top_industry_mv_to_equity_fund": [{"rank_num": 1, "value": 24.59}],
            },
        },
    )
    monkeypatch.setattr(
        "etf_agent.name_resolver.resolve_fundcode_from_name",
        lambda question, config, dry_run=False: {
            "status": "matched",
            "fundcode": "510880",
            "matched_name": "中证红利ETF",
            "matched_thscode": "510880.SH",
        },
    )

    result = semantic_query_v3(question, root=ROOT, dry_run=False, no_llm=False, phase="v3.3")

    assert result["failure_stage"] is None
    assert result["v3"]["recognized_query_mode"] == "composite"
    assert result["v3"]["intent"] == "two_step_composite"
    assert result["result"]["success"] is True
    assert "中证红利ETF" in result["answer"]
    assert "银行" in result["answer"]


def test_v3_3_semantic_query_marks_explicit_missing_report_as_data_not_available():
    result = semantic_query_v3("510300的持仓行业是什么（季报年报都没有）", root=ROOT, phase="v3.3")

    assert result["failure_stage"] == "data_not_available"
    assert result["v3"]["routing_result"]["type"] == "UnsupportedQuery"
    assert result["v3"]["routing_result"]["reason"] == "data_not_available"
    assert result["v3"]["remote_query_allowed"] is False
    assert result["query_plan"] is None
    assert "暂无" in result["answer"]


def test_v3_3_peer_average_period_semantics_remain_blocked_by_verification():
    result = semantic_query_v3("510300近半年收益率和同类平均比怎么样", root=ROOT, phase="v3.3")

    assert result["v3"]["routing_result"]["type"] == "UnsupportedQuery"
    assert result["v3"]["routing_result"]["reason"] == "blocked_by_verification"
    assert result["v3"]["remote_query_allowed"] is False
    assert result["query_plan"] is None
    assert result["v3"].get("ast_generation_mode") is None


def test_v3_3_validator_rejects_legacy_yield_field_as_return_semantics():
    bundle = build_generation_bundle(
        "510300按净值序列重新计算近一年收益率是多少",
        query_mode="single",
        intent="performance",
        entity_hints={"fundcodes": ["510300"], "period": "1y"},
        phase="v3.3",
    )
    draft = _derived_draft(
        select=["fundcode", "ths_yeild_1y_fund"],
        answer_fields=[
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_yeild_1y_fund", "format": "percent"},
        ],
        performance_rows=[],
    )

    with pytest.raises(ValueError, match="legacy yield field"):
        validate_v3_3_ast_draft(
            draft,
            query_mode="single",
            intent="performance",
            generation_bundle=bundle,
        )


def test_v3_3_validator_rejects_rank_origin_order_by():
    bundle = build_generation_bundle(
        "今年以来同类排名的ETF按名次排序",
        query_mode="filter",
        intent="filter",
        entity_hints={
            "fundcodes": [],
            "period": "ytd",
            "filters": [],
            "order_by": {"field": "ths_yeild_rank_ytd_fund", "direction": "asc"},
            "limit_hint": 10,
        },
        phase="v3.3",
    )
    draft = _derived_draft(
        profile="rank_list",
        intent="filter",
        output_style="list",
        select=[
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_yeild_rank_ytd_fund",
            "ths_yeild_rank_ytd_fund_origin",
        ],
        where=[],
        order_by={"field": "ths_yeild_rank_ytd_fund_origin", "direction": "asc"},
        limit=10,
        answer_fields=[
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_yeild_rank_ytd_fund", "format": "plain"},
            {"field": "ths_yeild_rank_ytd_fund_origin", "format": "plain"},
        ],
        performance_rows=[],
    )

    with pytest.raises(ValueError, match="_fund_origin"):
        validate_v3_3_ast_draft(
            draft,
            query_mode="filter",
            intent="filter",
            generation_bundle=bundle,
        )


def test_v3_3_semantic_query_compiles_and_executes_derived_performance(monkeypatch):
    draft = _derived_draft()

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_mongo_phase",
        lambda mongo_phase, config_obj: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_unit_nv_fund": [
                    {"btime": "2024-01-01", "value": 1.0},
                    {"btime": "2024-12-31", "value": 1.25},
                ],
            },
        },
    )

    result = semantic_query_v3("510300按净值序列重新计算近一年收益率是多少", root=ROOT)

    assert result["v3"]["ast_schema_version"] == "v3_3_structured_query"
    assert result["v3"]["grammar_fragment_id"] == "derived_performance"
    assert result["compiled_query"]["mongo_phase"]["projection"] == [
        "fundcode",
        "ths_unit_nv_fund",
        "ths_fund_extended_inner_short_name_fund",
    ]
    assert result["compiled_query"]["derived_phase"]["metrics"][0]["alias"] == "return_1y"
    assert result["result"]["derived_audit"]["derived_value_valid_count"] == 1
    assert result["result"]["data"]["return_1y"] == 25.0
    assert "25.00%" in _answer_body(result["answer"])


def test_v3_3_semantic_query_uses_remote_yield_fields_for_standard_performance(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "performance",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_yeild_1y_fund",
            "ths_yeild_rank_1y_fund_origin",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "159919"}],
        "order_by": None,
        "limit": 1,
        "output_style": "performance_table",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_yeild_1y_fund", "format": "percent"},
            {"field": "ths_yeild_rank_1y_fund_origin", "format": "plain"},
        ],
        "timeseries_semantics": None,
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": {
                "fundcode": "159919",
                "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                "ths_yeild_1y_fund": 10.23,
                "ths_yeild_rank_1y_fund_origin": "7362/22995",
            },
        },
    )

    result = semantic_query_v3("159919近1年收益，同类排名第几", root=ROOT, phase="v3.3")

    assert result["compiled_query"]["projection"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_yeild_1y_fund",
        "ths_yeild_rank_1y_fund_origin",
        "ths_unit_nv_fund",
    ]
    assert all(not field.startswith("return_") for field in result["validated_ast"]["select"])
    assert "10.23%" in result["answer"]
    assert "7362/22995" in result["answer"]


def test_v3_3_semantic_query_exposes_real_data_window_and_token_usage(monkeypatch):
    draft = _derived_draft()

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {
            "raw": json.dumps(draft, ensure_ascii=False),
            "draft": draft,
            "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        },
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_mongo_phase",
        lambda mongo_phase, config_obj: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_unit_nv_fund": [
                    {"btime": "2024-01-02", "value": 1.0},
                    {"btime": "2024-12-31", "value": 1.25},
                ],
            },
        },
    )

    result = semantic_query_v3("510300按净值序列重新计算近一年收益率是多少", root=ROOT)

    assert result["llm_usage"] == [{"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}]
    assert "查询起始时间：" not in result["answer"]
    assert "查询结束时间：" not in result["answer"]
    assert "数据起始日：2024-01-02" in result["answer"]
    assert "数据结束日：2024-12-31" in result["answer"]
    assert "LLM token：168" in result["answer"]
    assert "prompt_tokens=" not in result["answer"]


def test_v3_3_ast_draft_propagates_llm_errors_without_local_fallback(monkeypatch):
    fake_openai = ModuleType("openai")

    class _FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("boom")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    fake_openai.OpenAI = _FakeClient
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    config = SimpleNamespace(dashscope_api_key="key", dashscope_base_url="url", llm_model="model")

    with pytest.raises(RuntimeError, match="boom"):
        generate_full_ast_draft_with_llm(
            question="510300按净值序列重新计算近一年收益率是多少",
            routing_result={"recognized_query_mode": "single"},
            classification={"intent": "performance"},
            generation_context={"llm_context": {}},
            config=config,
        )


def test_v3_3_semantic_query_formats_performance_table_when_rows_metadata_missing(monkeypatch):
    draft = _derived_draft()
    draft.pop("grammar_fragment_id")
    draft.pop("compiler_rule_id")
    draft.pop("profile")
    draft.pop("performance_rows")

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_mongo_phase",
        lambda mongo_phase, config_obj: {
            "success": True,
            "data": {
                "fundcode": "510300",
                "ths_unit_nv_fund": [
                    {"btime": "2024-01-01", "value": 1.0},
                    {"btime": "2024-12-31", "value": 1.25},
                ],
            },
        },
    )

    result = semantic_query_v3("510300按净值序列重新计算近一年收益率是多少", root=ROOT)

    assert result["failure_stage"] is None
    assert result["compiled_query"]["compiler_rule_id"] == "derived_performance_table"
    assert result["compiled_query"]["output_phase"]["performance_rows"] == [
        {"alias": "return_1y", "period": "1y", "label": "近1年收益率"}
    ]
    assert "25.00%" in result["answer"]


def test_v3_3_semantic_query_uses_year_to_date_yield_for_top10_filter(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_yeild_ytd_fund"],
        "where": [],
        "order_by": {"field": "ths_yeild_ytd_fund", "direction": "desc"},
        "limit": 10,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": [
                {
                    "fundcode": "510300",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_ytd_fund": 5.55,
                },
                {
                    "fundcode": "159919",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_ytd_fund": 5.20,
                },
            ],
        },
    )

    result = semantic_query_v3("今年以来收益排名前10的ETF", root=ROOT, dry_run=False, no_llm=False, phase="v3.3")

    assert _answer_body(result["answer"]).startswith("| 基金代码 | 基金简称 | 今年以来收益率 |")
    assert "5.55%" in result["answer"]
    assert result["compiled_query"]["sort"][0] == ["ths_yeild_ytd_fund", -1]
    assert "ths_unit_nv_fund" in result["compiled_query"]["projection"]


def test_v3_3_semantic_query_uses_one_year_yield_for_above_threshold_filter(monkeypatch):
    draft = {
        "ast_schema_version": "v3_3_structured_query",
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_yeild_1y_fund"],
        "where": [
            {"field": "ths_yeild_1y_fund", "op": "gt", "value": 20.0},
        ],
        "order_by": {"field": "ths_yeild_1y_fund", "direction": "desc"},
        "limit": 50,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_yeild_1y_fund", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": [
                {
                    "fundcode": "510300",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_1y_fund": 29.98,
                },
                {
                    "fundcode": "159919",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_1y_fund": 21.10,
                },
            ],
        },
    )

    result = semantic_query_v3("近1年收益率超过20%的ETF", root=ROOT, dry_run=False, no_llm=False, phase="v3.3")

    assert _answer_body(result["answer"]).startswith("| 基金代码 | 基金简称 | 近1年收益率 |")
    assert "29.98%" in result["answer"]
    assert result["compiled_query"]["filter"] == {"ths_yeild_1y_fund": {"$gt": 20.0}}
    assert result["compiled_query"]["sort"][0] == ["ths_yeild_1y_fund", -1]
    assert "ths_unit_nv_fund" in result["compiled_query"]["projection"]
