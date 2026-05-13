from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from etf_agent.capability_registry import get_selection_context
from etf_agent.v3 import classify_v3_query, semantic_query_v3


ROOT = Path(__file__).resolve().parents[1]


def test_v3_2_registry_exposes_basic_info_extended_and_date_filter_fields():
    context = get_selection_context("single", "basic_info_extended", phase="v3.2")

    assert context["field_profile"] == "basic_info_extended"
    assert context["semantic_roles"]["fundcode"] == "identity"
    assert context["semantic_roles"]["ths_fund_extended_inner_short_name_fund"] == "context"
    assert context["semantic_roles"]["ths_fund_establishment_date_fund"] == "semantic"
    assert "ths_fund_establishment_date_fund" in context["selectable_fields"]
    assert "ths_perf_comparative_benchmark_fund" in context["selectable_fields"]
    assert "ths_pur_and_redemp_status_fund" in context["selectable_fields"]
    assert "ths_etf_to_code_fund" in context["selectable_fields"]
    assert context["field_operators"]["ths_fund_establishment_date_fund"] == ["eq", "gte", "lte", "between"]
    assert context["gates"]["ths_fund_establishment_date_fund"] == "always"


def test_v3_2_generation_context_exposes_strict_validation_contract():
    from etf_agent.generation_context import build_generation_bundle

    bundle = build_generation_bundle(
        "510300成立以来收益怎么样，分过红吗",
        query_mode="single",
        intent="composite_single",
        entity_hints={"fundcodes": ["510300"], "period": "std"},
        phase="v3.2",
    )

    contract = bundle["llm_context"]["strict_validation_contract"]
    assert contract["required_select_fields"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_yeild_std_fund",
        "ths_accum_dividend_total_amt_fund",
        "ths_accum_dividend_times_fund",
    ]
    assert contract["expected_sub_intents"] == ["performance", "dividend"]
    assert contract["expected_where"] == [{"field": "fundcode", "op": "eq", "value": "510300"}]


def test_v3_2_single_query_uses_llm_ast_draft_path(monkeypatch):
    draft = {
        "intent": "basic_info_extended",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_fund_establishment_date_fund"],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_fund_establishment_date_fund", "label": "成立日期", "format": "date"},
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
                "ths_fund_establishment_date_fund": "2024-01-01",
            },
        },
    )

    result = semantic_query_v3("510300的成立日期是什么时候", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["v3"]["llm_ast_draft_raw"]
    assert result["v3_ast"]["intent"] == "basic_info_extended"
    assert result["validated_ast"]["select"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_establishment_date_fund",
    ]
    assert result["mongo_params"]["collection"] == "tb_ths_etf_base"
    assert "2024-01-01" in result["answer"]
    assert result["v3"]["remote_query_allowed"] is True
    assert set(result["v3"]["provenance_diff"]) == {
        "draft_semantics",
        "validated_semantics",
        "compiler_expansions",
        "validator_additions_by_kind",
        "semantic_additions",
        "semantic_overrides",
        "strict_pass",
    }
    assert result["v3"]["provenance_diff"]["semantic_additions"] == []
    assert result["v3"]["provenance_diff"]["semantic_overrides"] == []
    assert result["v3"]["provenance_diff"]["validator_additions_by_kind"]["semantic"] == []
    assert result["v3"]["provenance_diff"]["strict_pass"] is True
    assert result["v3"]["capability_id"] == "v3.2:single:basic_info_extended"
    assert result["v3"]["capability_status"] == "executable"
    assert result["v3"]["gate_status"] in {"passed", "not_applicable"}


def test_v3_2_validator_rejects_missing_requested_semantic_field(monkeypatch):
    draft = {
        "intent": "basic_info_extended",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode"],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )

    result = semantic_query_v3("510300的成立日期是什么时候", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["failure_stage"] == "validator"
    assert "成立日期" in result["failure_reason"]
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft_failed"
    assert result["v3"]["remote_query_allowed"] is False
    assert result["v3"]["capability_id"] == "v3.2:single:basic_info_extended"
    assert result["v3"]["capability_status"] == "failed"
    assert result["v3"]["gate_status"] == "passed"
    assert result["v3"]["capability_status_reason"] == "validator"
    assert result["v3_ast"] is None


def test_v3_2_legacy_provenance_does_not_repair_semantic_baseline_field():
    from etf_agent.ast_validator import validate_v3_2_ast_draft
    from etf_agent.generation_context import build_generation_bundle

    bundle = build_generation_bundle(
        "510300是什么",
        query_mode="single",
        intent="basic_info",
        entity_hints={"fundcodes": ["510300"]},
        phase="v3.2",
    )
    draft = {
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
    bundle["selection_context"]["baseline_answer_fields"].append("ths_manage_fee_rate_fund")
    bundle["selection_context"]["selectable_fields"].append("ths_manage_fee_rate_fund")
    bundle["selection_context"]["field_metas"]["ths_manage_fee_rate_fund"] = {
        "label": "管理费率",
        "format": "percent",
    }
    bundle["selection_context"]["semantic_roles"]["ths_manage_fee_rate_fund"] = "semantic"

    result = validate_v3_2_ast_draft(
        draft,
        query_mode="single",
        intent="basic_info",
        generation_bundle=bundle,
    )

    diff = result["provenance_diff"]
    assert "ths_manage_fee_rate_fund" not in result["validated_ast"]["select"]
    assert diff["validator_additions_by_kind"]["semantic"] == []
    assert diff["semantic_additions"] == []
    assert diff["strict_pass"] is True


def test_v3_2_validator_does_not_auto_add_semantic_baseline_field():
    from etf_agent.ast_validator import validate_v3_2_ast_draft
    from etf_agent.generation_context import build_generation_bundle

    bundle = build_generation_bundle(
        "510300是什么",
        query_mode="single",
        intent="basic_info",
        entity_hints={"fundcodes": ["510300"]},
        phase="v3.2",
    )
    draft = {
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
    bundle["selection_context"]["baseline_answer_fields"].append("ths_manage_fee_rate_fund")
    bundle["selection_context"]["selectable_fields"].append("ths_manage_fee_rate_fund")
    bundle["selection_context"]["field_metas"]["ths_manage_fee_rate_fund"] = {
        "label": "管理费率",
        "format": "percent",
    }
    bundle["selection_context"]["semantic_roles"]["ths_manage_fee_rate_fund"] = "semantic"

    result = validate_v3_2_ast_draft(
        draft,
        query_mode="single",
        intent="basic_info",
        generation_bundle=bundle,
    )

    diff = result["provenance_diff"]
    assert "ths_manage_fee_rate_fund" not in result["validated_ast"]["select"]
    assert diff["validator_additions_by_kind"]["semantic"] == []
    assert diff["semantic_additions"] == []
    assert diff["strict_pass"] is True


def test_v3_2_validator_normalizes_select_object_aliases(monkeypatch):
    draft = {
        "intent": "basic_info",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            {"field": "fundcode", "alias": "fund_code"},
            {"field": "ths_fund_extended_inner_short_name_fund", "alias": "fund_short_name"},
            {"field": "ths_name_of_tracking_index_fund", "alias": "tracking_index"},
            {"field": "ths_fund_scale_fund", "alias": "fund_scale"},
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fund_code", "label": "基金代码", "format": "plain"},
            {"field": "fund_short_name", "label": "基金简称", "format": "plain"},
            {"field": "tracking_index", "label": "跟踪指数名称", "format": "plain"},
            {"field": "fund_scale", "label": "基金规模", "format": "amount"},
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
                "ths_name_of_tracking_index_fund": "沪深300",
                "ths_fund_scale_fund": 100000000,
            },
        },
    )

    result = semantic_query_v3("510300是什么", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["validated_ast"]["select"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_name_of_tracking_index_fund",
        "ths_fund_scale_fund",
    ]
    assert [item["field"] for item in result["validated_ast"]["answer_fields"][:4]] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_name_of_tracking_index_fund",
        "ths_fund_scale_fund",
    ]


@pytest.mark.parametrize(
    ("question", "rank_field", "yield_field", "rank_label", "rank_value"),
    [
        ("510300近2年ETF排第几", "ths_yeild_rank_2y_etf", "ths_yeild_2y_fund", "近2年 ETF 排名", "3"),
        ("510300今年在同类基金里排多少", "ths_yeild_rank_ytd_fund_origin", "ths_yeild_ytd_fund", "今年以来同类排名", "1/10"),
    ],
)
def test_v3_2_rank_only_performance_queries_do_not_require_yield_fields(
    monkeypatch,
    question,
    rank_field,
    yield_field,
    rank_label,
    rank_value,
):
    draft = {
        "intent": "performance",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", rank_field],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": rank_field, "label": rank_label, "format": "plain"},
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
                rank_field: rank_value,
            },
        },
    )

    result = semantic_query_v3(question, root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert rank_field in result["validated_ast"]["select"]
    assert yield_field not in result["validated_ast"]["select"]
    assert rank_value in result["answer"]


def test_v3_2_filter_between_date_draft_is_normalized_to_range(monkeypatch):
    draft = {
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_scale_fund",
            "ths_manage_fee_rate_fund",
            "ths_fund_listed_exchange_fund",
            "ths_fund_invest_type_fund",
            "ths_name_of_tracking_index_fund",
            "ths_fund_establishment_date_fund",
        ],
        "where": [
            {
                "field": "ths_fund_establishment_date_fund",
                "op": "between",
                "value": ["2024-01-01", "2024-12-31"],
            }
        ],
        "order_by": None,
        "limit": 10,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_fund_scale_fund", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "format": "percent"},
            {"field": "ths_fund_listed_exchange_fund", "format": "plain"},
            {"field": "ths_fund_invest_type_fund", "format": "plain"},
            {"field": "ths_name_of_tracking_index_fund", "format": "plain"},
            {"field": "ths_fund_establishment_date_fund", "format": "date"},
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
                    "ths_fund_establishment_date_fund": "2024-01-15",
                }
            ],
        },
    )

    result = semantic_query_v3("2024年成立的ETF有哪些", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["validated_ast"]["where"] == [
        {"field": "ths_fund_establishment_date_fund", "op": "gte", "value": "2024-01-01", "raw_value": "2024年"},
        {"field": "ths_fund_establishment_date_fund", "op": "lte", "value": "2024-12-31", "raw_value": "2024年"},
    ]


def test_v3_2_data_query_about_subscription_redemption_does_not_deny(monkeypatch):
    monkeypatch.setattr(
        "etf_agent.v3._match_by_embedding",
        lambda question, config: (None, "investment_advice"),
    )

    result = classify_v3_query(
        "华泰柏瑞沪深300ETF现在申赎是开着还是关着？",
        {},
        config=SimpleNamespace(dashscope_api_key=""),
    )

    assert result["recognized_query_mode"] in {"single", "clarify"}
    assert result.get("intent") != "deny"
    assert result.get("deny_reason") != "investment_advice"


def test_v3_2_implicit_search_signal_routes_to_search_not_single(monkeypatch):
    monkeypatch.setattr(
        "etf_agent.v3._match_by_embedding",
        lambda question, config: (None, "investment_advice"),
    )

    result = classify_v3_query(
        "名字里或者标的指数里有新能源的ETF给我看看",
        {},
        config=SimpleNamespace(dashscope_api_key=""),
    )

    assert result["recognized_query_mode"] in {"search", "filter"}
    assert result["intent"] in {"search", "filter"}
    assert result["intent"] != "basic_info"


def test_v3_2_composite_single_emits_all_requested_single_sub_intents(monkeypatch):
    draft = {
        "intent": "composite_single",
        "sub_intents": ["performance", "manager", "basic_info_extended"],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_yeild_std_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
            "ths_pur_and_redemp_status_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_yeild_std_fund", "format": "percent"},
            {"field": "ths_fund_manager_current_fund", "format": "plain"},
            {"field": "ths_fund_supervisor_fund", "format": "plain"},
            {"field": "ths_pur_and_redemp_status_fund", "format": "plain"},
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
                "ths_yeild_std_fund": 12.3,
                "ths_fund_manager_current_fund": "张三",
                "ths_fund_supervisor_fund": "华泰柏瑞基金管理有限公司",
                "ths_pur_and_redemp_status_fund": "开着",
            },
        },
    )

    result = semantic_query_v3("510300收益、管理人、申赎状态能不能一次查？", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["intent"] == "composite_single"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["v3"]["routing_evidence"]["why_not_single"]
    assert "performance" in result["v3"]["routing_evidence"]["semantic_constraints"]["sub_intents"]
    assert result["validated_ast"]["sub_intents"] == ["performance", "manager", "basic_info_extended"]


def test_v3_2_established_since_return_routes_to_performance_not_composite():
    result = classify_v3_query(
        "510500成立以来收益怎么样",
        {"fundcode": "510500", "period": "std"},
        config=SimpleNamespace(dashscope_api_key=""),
    )

    assert result["recognized_query_mode"] == "single"
    assert result["intent"] == "performance"
    assert result["entity_hints"]["period"] == "std"


def test_v3_2_composite_return_and_dividend_does_not_require_rank_fields(monkeypatch):
    draft = {
        "intent": "composite_single",
        "sub_intents": ["performance", "dividend"],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_yeild_std_fund",
            "ths_accum_dividend_total_amt_fund",
            "ths_accum_dividend_times_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_yeild_std_fund", "format": "percent"},
            {"field": "ths_accum_dividend_total_amt_fund", "format": "amount"},
            {"field": "ths_accum_dividend_times_fund", "format": "plain"},
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
                "ths_yeild_std_fund": 12.3,
                "ths_accum_dividend_total_amt_fund": 1000000,
                "ths_accum_dividend_times_fund": 2,
            },
        },
    )

    result = semantic_query_v3("510300成立以来收益怎么样，分过红吗", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["intent"] == "composite_single"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["validated_ast"]["sub_intents"] == ["performance", "dividend"]
    assert "ths_yeild_rank_std_fund_origin" not in result["validated_ast"]["select"]
    assert "ths_yeild_rank_std_etf" not in result["validated_ast"]["select"]


def test_v3_2_composite_single_rejects_missing_requested_sub_intents(monkeypatch):
    draft = {
        "intent": "composite_single",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_yeild_std_fund",
            "ths_accum_dividend_total_amt_fund",
            "ths_accum_dividend_times_fund",
        ],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_yeild_std_fund", "format": "percent"},
            {"field": "ths_accum_dividend_total_amt_fund", "format": "amount"},
            {"field": "ths_accum_dividend_times_fund", "format": "plain"},
        ],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        lambda **kwargs: {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft},
    )

    result = semantic_query_v3("510300成立以来收益怎么样，分过红吗", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["failure_stage"] == "validator"
    assert "sub_intents" in result["failure_reason"]
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft_failed"


def test_v3_2_which_is_better_is_denied_as_investment_advice():
    result = classify_v3_query(
        "512880和510300哪个更好",
        {"fundcode": "512880", "period": "1y"},
        config=SimpleNamespace(dashscope_api_key=""),
    )

    assert result["recognized_query_mode"] == "deny"
    assert result["deny_reason"] == "investment_advice"



def test_v3_2_filter_tracking_index_alias_is_normalized(monkeypatch):
    draft = {
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_name_of_tracking_index_fund",
            "ths_yeild_std_fund",
        ],
        "where": [{"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "沪深300"}],
        "order_by": {"field": "ths_yeild_std_fund", "direction": "desc"},
        "limit": 1,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_name_of_tracking_index_fund", "format": "plain"},
            {"field": "ths_yeild_std_fund", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }

    monkeypatch.setattr(
        "etf_agent.v3._resolve_v3_1_index_filters",
        lambda entity_hints, config_obj, *, dry_run: {
            **entity_hints,
            "filters": [
                {
                    "field": "ths_name_of_tracking_index_fund",
                    "op": "eq",
                    "value": "沪深300指数",
                    "raw_value": "沪深300",
                }
            ],
        },
    )
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
                    "ths_name_of_tracking_index_fund": "沪深300指数",
                    "ths_yeild_std_fund": 12.3,
                }
            ],
        },
    )

    result = semantic_query_v3("成立以来收益最好的沪深300ETF是哪只", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["validated_ast"]["where"] == [
        {
            "field": "ths_name_of_tracking_index_fund",
            "op": "eq",
            "value": "沪深300指数",
            "raw_value": "沪深300",
        }
    ]
    assert result["validated_ast"]["order_by"] == {"field": "ths_yeild_std_fund", "direction": "desc"}


def test_v3_2_compare_null_limit_defaults_to_compare_cap(monkeypatch):
    draft = {
        "intent": "compare",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_scale_fund",
            "ths_manage_fee_rate_fund",
            "ths_mandate_fee_rate_fund",
            "ths_yeild_ytd_fund",
            "ths_yeild_1y_fund",
            "ths_name_of_tracking_index_fund",
        ],
        "where": [{"field": "fundcode", "op": "in", "value": ["510300", "510500", "159919"]}],
        "order_by": None,
        "limit": None,
        "output_style": "compare",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_fund_scale_fund", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "format": "percent"},
            {"field": "ths_mandate_fee_rate_fund", "format": "percent"},
            {"field": "ths_yeild_ytd_fund", "format": "percent"},
            {"field": "ths_yeild_1y_fund", "format": "percent"},
            {"field": "ths_name_of_tracking_index_fund", "format": "plain"},
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
                {"fundcode": "510300", "ths_fund_extended_inner_short_name_fund": "沪深300ETF"},
                {"fundcode": "510500", "ths_fund_extended_inner_short_name_fund": "中证500ETF"},
                {"fundcode": "159919", "ths_fund_extended_inner_short_name_fund": "创业板ETF"},
            ],
        },
    )

    result = semantic_query_v3("对比510300、510500和159919", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["validated_ast"]["limit"] == 10
    assert result["mongo_params"]["limit"] == 10


def test_v3_2_filter_order_by_singleton_list_is_normalized(monkeypatch):
    draft = {
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_scale_fund",
            "ths_manage_fee_rate_fund",
            "ths_yeild_ytd_fund",
        ],
        "where": [],
        "order_by": [{"field": "ths_yeild_ytd_fund", "direction": "desc"}],
        "limit": 10,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "format": "plain"},
            {"field": "ths_fund_scale_fund", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "format": "percent"},
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
                    "ths_yeild_ytd_fund": 12.3,
                }
            ],
        },
    )

    result = semantic_query_v3("今年以来收益排名前10的ETF", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["validated_ast"]["order_by"] == {"field": "ths_yeild_ytd_fund", "direction": "desc"}


def test_v3_2_filter_select_does_not_need_to_repeat_predicate_fields(monkeypatch):
    filter_draft = {
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_manage_fee_rate_fund",
            "ths_yeild_ytd_fund",
        ],
        "where": [
            {"field": "ths_fund_listed_exchange_fund", "op": "eq", "value": "上交所"},
        ],
        "order_by": {"field": "ths_manage_fee_rate_fund", "direction": "asc"},
        "limit": 3,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }
    compare_draft = {
        "intent": "compare",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_yeild_ytd_fund"],
        "where": [{"field": "fundcode", "op": "in", "value": ["510300", "510500", "159919"]}],
        "order_by": None,
        "limit": 10,
        "output_style": "compare",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }
    drafts = iter([filter_draft, compare_draft])

    def fake_generate_full_ast_draft_with_llm(**kwargs):
        draft = next(drafts)
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft}

    call_state = {"count": 0}

    def fake_execute_v3_plan(plan, config_obj, *, dry_run, no_llm):
        call_state["count"] += 1
        if call_state["count"] == 1:
            return {
                "success": True,
                "data": [
                    {
                        "fundcode": "510300",
                        "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                        "ths_manage_fee_rate_fund": 0.15,
                        "ths_yeild_ytd_fund": 12.3,
                    },
                    {
                        "fundcode": "510500",
                        "ths_fund_extended_inner_short_name_fund": "中证500ETF",
                        "ths_manage_fee_rate_fund": 0.18,
                        "ths_yeild_ytd_fund": 10.1,
                    },
                    {
                        "fundcode": "159919",
                        "ths_fund_extended_inner_short_name_fund": "创业板ETF",
                        "ths_manage_fee_rate_fund": 0.2,
                        "ths_yeild_ytd_fund": 8.6,
                    },
                ],
            }
        return {
            "success": True,
            "data": [
                {
                    "fundcode": "510300",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_ytd_fund": 12.3,
                },
                {
                    "fundcode": "510500",
                    "ths_fund_extended_inner_short_name_fund": "中证500ETF",
                    "ths_yeild_ytd_fund": 10.1,
                },
                {
                    "fundcode": "159919",
                    "ths_fund_extended_inner_short_name_fund": "创业板ETF",
                    "ths_yeild_ytd_fund": 8.6,
                },
            ],
        }

    monkeypatch.setattr("etf_agent.v3.generate_full_ast_draft_with_llm", fake_generate_full_ast_draft_with_llm)
    monkeypatch.setattr("etf_agent.v3._execute_v3_plan", fake_execute_v3_plan)

    result = semantic_query_v3("上交所的ETF里，找管理费最低的3只，对比它们的今年收益", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "compare"
    assert result["v3"]["intent"] == "two_step_composite"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"


def test_v3_2_filter_to_compare_step2_prompt_forbids_order_by(monkeypatch):
    filter_draft = {
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_scale_fund",
            "ths_manage_fee_rate_fund",
            "ths_fund_invest_type_fund",
            "ths_yeild_ytd_fund",
        ],
        "where": [{"field": "ths_fund_invest_type_fund", "op": "eq", "value": "股票型"}],
        "order_by": {"field": "ths_yeild_ytd_fund", "direction": "desc"},
        "limit": 5,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
            {"field": "ths_fund_invest_type_fund", "label": "基金投资类型", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }
    compare_draft = {
        "intent": "compare",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_yeild_ytd_fund"],
        "where": [{"field": "fundcode", "op": "in", "value": ["513310", "588780", "589210", "159663", "159667"]}],
        "order_by": None,
        "limit": 5,
        "output_style": "compare",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }
    contexts: list[str] = []
    drafts = iter([filter_draft, compare_draft])

    def fake_generate_full_ast_draft_with_llm(**kwargs):
        contexts.append(kwargs["generation_context"]["llm_context"]["child_task"])
        draft = next(drafts)
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft}

    monkeypatch.setattr("etf_agent.v3.generate_full_ast_draft_with_llm", fake_generate_full_ast_draft_with_llm)
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": [
                {
                    "fundcode": "513310",
                    "ths_fund_extended_inner_short_name_fund": "ETF1",
                    "ths_yeild_ytd_fund": 12.3,
                },
                {
                    "fundcode": "588780",
                    "ths_fund_extended_inner_short_name_fund": "ETF2",
                    "ths_yeild_ytd_fund": 10.1,
                },
                {
                    "fundcode": "589210",
                    "ths_fund_extended_inner_short_name_fund": "ETF3",
                    "ths_yeild_ytd_fund": 8.6,
                },
                {
                    "fundcode": "159663",
                    "ths_fund_extended_inner_short_name_fund": "ETF4",
                    "ths_yeild_ytd_fund": 7.4,
                },
                {
                    "fundcode": "159667",
                    "ths_fund_extended_inner_short_name_fund": "ETF5",
                    "ths_yeild_ytd_fund": 6.2,
                },
            ],
        },
    )

    result = semantic_query_v3("股票型ETF里今年收益最高的5只是哪些？对比一下", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "compare"
    assert result["v3"]["intent"] == "two_step_composite"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert len(contexts) == 2
    assert "step 2" in contexts[1]
    assert "order_by" in contexts[1]


def test_v3_2_manager_detail_does_not_fallback_to_manager(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError("manager_detail blocked query must not enter AST generation")

    monkeypatch.setattr("etf_agent.v3.generate_full_ast_draft_with_llm", fail_if_called)

    result = semantic_query_v3("510300基金经理的历史业绩怎么样", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["routing_result"]["type"] == "UnsupportedQuery"
    assert result["v3"]["failure_reason"] == "blocked_by_verification"
    assert result["v3"]["ast_generation_mode"] is None
    assert result["v3"]["remote_query_allowed"] is False
    assert result["v3"]["capability_id"] == "v3.2:unsupported:blocked_by_verification"
    assert result["v3"]["capability_status"] == "blocked_by_verification"
    assert result["v3"]["gate_status"] == "blocked"
    assert result["v3"]["capability_status_reason"] == "blocked_by_verification"
    assert result["v3_ast"] is None
    assert result["validated_ast"] is None


def test_v3_2_two_step_composite_uses_llm_ast_for_each_child(monkeypatch):
    filter_draft = {
        "intent": "filter",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_scale_fund",
            "ths_manage_fee_rate_fund",
            "ths_fund_invest_type_fund",
            "ths_yeild_ytd_fund",
        ],
        "where": [{"field": "ths_fund_invest_type_fund", "op": "eq", "value": "股票型"}],
        "order_by": {"field": "ths_yeild_ytd_fund", "direction": "desc"},
        "limit": 5,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
            {"field": "ths_fund_invest_type_fund", "label": "基金投资类型", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }
    compare_draft = {
        "intent": "compare",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_yeild_ytd_fund"],
        "where": [{"field": "fundcode", "op": "in", "value": ["510300", "510500"]}],
        "order_by": None,
        "limit": 10,
        "output_style": "compare",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
        ],
        "report_period": None,
        "expand": None,
    }
    drafts = iter([filter_draft, compare_draft])

    def fake_generate_full_ast_draft_with_llm(**kwargs):
        draft = next(drafts)
        return {"raw": json.dumps(draft, ensure_ascii=False), "draft": draft}

    monkeypatch.setattr(
        "etf_agent.v3.generate_full_ast_draft_with_llm",
        fake_generate_full_ast_draft_with_llm,
    )
    monkeypatch.setattr(
        "etf_agent.v3._execute_v3_plan",
        lambda plan, config_obj, *, dry_run, no_llm: {
            "success": True,
            "data": [
                {
                    "fundcode": "510300",
                    "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
                    "ths_yeild_ytd_fund": 12.3,
                },
                {
                    "fundcode": "510500",
                    "ths_fund_extended_inner_short_name_fund": "中证500ETF",
                    "ths_yeild_ytd_fund": 10.1,
                },
            ],
        },
    )

    result = semantic_query_v3("股票型ETF里今年收益最高的5只是哪些？对比一下", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "compare"
    assert result["v3"]["intent"] == "two_step_composite"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["v3"]["steps"] == [
        {"recognized_query_mode": "filter", "intent": "filter"},
        {"recognized_query_mode": "compare", "intent": "compare"},
    ]
    assert result["result"]["success"] is True
    assert all(step["success"] is True for step in result["result"]["steps"])
    assert "510300" in result["answer"]
    assert "510500" in result["answer"]
def test_v3_2_invalid_ascii_code_raises_clarification():
    result = semantic_query_v3("abcdef是什么基金", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "clarify"
    assert result["v3"]["routing_result"]["type"] == "ClarificationRequired"
    assert result["v3"]["ast_generation_mode"] is None
    assert result["v3_ast"] is None
    assert "有效的 ETF 代码" in result["answer"]


def test_v3_2_search_signal_beats_track_filter(monkeypatch):
    draft = {
        "intent": "search",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_fund_scale_fund", "ths_manage_fee_rate_fund"],
        "where": [{"field": "__search_text__", "op": "contains", "value": "科创50"}],
        "order_by": None,
        "limit": 20,
        "output_style": "list",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
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
        lambda plan, config_obj, *, dry_run, no_llm: {"success": True, "data": []},
    )

    result = semantic_query_v3("我想找跟踪科创50的ETF", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "search"
    assert result["v3"]["intent"] == "search"
    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert result["v3_ast"]["where"][0]["value"] == "科创50"


def test_v3_2_manager_history_query_is_blocked():
    result = semantic_query_v3("510300什么时候换的基金经理", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "unsupported"
    assert result["v3"]["routing_result"]["type"] == "UnsupportedQuery"
    assert result["failure_reason"] == "unsupported_manager_history"
    assert result["v3"]["remote_query_allowed"] is False
    assert result["v3_ast"] is None


def test_v3_2_fund_share_timeseries_query_is_blocked():
    result = semantic_query_v3("510300的基金份额最近有变化吗", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["recognized_query_mode"] == "unsupported"
    assert result["v3"]["routing_result"]["type"] == "UnsupportedQuery"
    assert result["failure_reason"] == "unsupported_timeseries"
    assert result["v3"]["remote_query_allowed"] is False
    assert result["v3_ast"] is None


def test_v3_2_performance_does_not_default_rank_fields(monkeypatch):
    draft = {
        "intent": "performance",
        "sub_intents": [],
        "from": "tb_ths_etf_base",
        "select": ["fundcode", "ths_yeild_ytd_fund"],
        "where": [{"field": "fundcode", "op": "eq", "value": "510300"}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_yeild_ytd_fund", "label": "今年以来收益率", "format": "percent"},
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
                "ths_yeild_ytd_fund": 12.3,
                "ths_yeild_rank_ytd_fund_origin": "1/10",
                "ths_yeild_rank_ytd_etf": 3,
            },
        },
    )

    result = semantic_query_v3("510300今年的收益率是多少", root=ROOT, dry_run=False, no_llm=False, phase="v3.2")

    assert result["v3"]["ast_generation_mode"] == "llm_ast_draft"
    assert "ths_yeild_rank_ytd_fund_origin" not in result["validated_ast"]["select"]
    assert "ths_yeild_rank_ytd_etf" not in result["validated_ast"]["select"]


def test_v3_2_audit_loads_every_coverage_matrix_row():
    from scripts.audit_v3_2_results import load_coverage_rows

    rows = load_coverage_rows(ROOT / "docs" / "v3-coverage-matrix.md")
    questions = [row["question"] for row in rows]

    assert len(rows) == len(set(questions))
    assert "510300的成立日期是什么时候" in questions
    assert "2024年成立的ETF有哪些" in questions
    assert "510300能买吗" in questions
    assert any(row["ast_generation_mode"] == "llm_ast_draft" for row in rows)


def test_v3_2_audit_script_uses_full_runtime_without_dry_run_or_no_llm():
    script = (ROOT / "scripts" / "audit_v3_2_results.py").read_text(encoding="utf-8")

    assert 'OUT_MD = ROOT / "answer" / "audit-v3.2-results.md"' in script
    assert 'OUT_JSON = ROOT / "answer" / "raw" / "audit-v3.2-results.json"' in script
    assert "dry_run=True" not in script
    assert "no_llm=True" not in script
    assert "semantic_query_v3(row.question" in script


def test_v3_2_audit_main_skips_out_of_scope_rows_without_runtime(monkeypatch, tmp_path):
    from scripts import audit_v3_2_results as audit

    rows = [
        audit.CoverageRow(
            {
                "question_id": "四.1",
                "question": "510300近半年收益率和同类平均比怎么样",
                "routing_result.type": "UnsupportedQuery",
                "recognized_query_mode": "null",
                "expected_intent_or_profile": "unsupported_peer_average",
                "ast_generation_mode": "null",
                "remote_query_allowed": "false",
                "llm_ast_draft_required": "false",
                "release_scope": "v3_3_required",
            }
        ),
        audit.CoverageRow(
            {
                "question_id": "一.1",
                "question": "510300是什么",
                "routing_result.type": "ExecutableQuery",
                "recognized_query_mode": "single",
                "expected_intent_or_profile": "basic_info",
                "ast_generation_mode": "llm_ast_draft",
                "remote_query_allowed": "true",
                "llm_ast_draft_required": "true",
                "release_scope": "v3_2_required",
            }
        ),
    ]
    calls = []

    def fake_semantic_query_v3(question, root, phase="v3.2"):
        calls.append(question)
        assert phase == "v3.2"
        return {
            "answer": "510300 是沪深300ETF。",
            "v3": {
                "routing_result": {"type": "ExecutableQuery"},
                "recognized_query_mode": "single",
                "intent": "basic_info",
                "ast_generation_mode": "llm_ast_draft",
                "remote_query_allowed": True,
                "llm_ast_draft_raw": "{}",
                "capability_status": "executable",
                "gate_status": "not_applicable",
                "provenance_diff": {
                    "strict_pass": True,
                    "semantic_additions": [],
                    "semantic_overrides": [],
                    "validator_additions_by_kind": {"semantic": []},
                },
            },
            "v3_ast": {"intent": "basic_info"},
            "validated_ast": {"intent": "basic_info"},
            "query_plan": {"collection": "tb_ths_etf_base"},
            "mongo_params": {"collection": "tb_ths_etf_base"},
            "result": {"success": True, "data": {}},
        }

    monkeypatch.setattr(audit, "load_coverage_rows", lambda path: rows)
    monkeypatch.setattr(audit, "semantic_query_v3", fake_semantic_query_v3)
    monkeypatch.setattr(audit, "OUT_JSON", tmp_path / "audit.json")
    monkeypatch.setattr(audit, "OUT_MD", tmp_path / "audit.md")

    exit_code = audit.main()

    assert exit_code == 0
    assert calls == ["510300是什么"]
    records = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert records[0]["status"] == "SKIP"
    assert records[0]["display_answer"] == "不在 v3.2 能力范围"


def test_v3_2_audit_markdown_uses_aligned_three_column_table():
    from scripts.audit_v3_2_results import _markdown

    records = [
        {
            "question_id": "一.1",
            "question": "510300是什么",
            "release_scope": "v3_2_required",
            "expected_type": "ExecutableQuery",
            "expected_mode": "single",
            "expected_intent": "basic_info",
            "actual_type": "ExecutableQuery",
            "actual_mode": "single",
            "actual_intent": "basic_info",
            "ast_generation_mode": "llm_ast_draft",
            "remote_query_allowed": True,
            "remote_status": "PASS",
            "formatter_status": "PASS",
            "failure_stage": None,
            "failure_reason": None,
            "query_summary": '{"collection":"tb_ths_etf_base"}',
            "status": "PASS",
            "reason": "",
            "answer": "510300 的基金简称为 沪深300ETF。",
        }
    ]

    md = _markdown(records)

    assert "```text" in md
    assert any(line.strip().startswith("ID") for line in md.splitlines())
    assert "预期 + 真实回答" in md
    assert "510300 的基金简称为 沪深300ETF。" in md
    assert "ExecutableQuery / single / basic_info" in md


def test_v3_2_audit_briefs_long_user_answers_for_markdown():
    from scripts.audit_v3_2_results import evaluate_row
    from scripts.audit_v3_2_results import CoverageRow

    row = CoverageRow(
        {
            "question_id": "一.9",
            "question": "510300的投资目标和策略是什么",
            "release_scope": "v3_2_required",
            "routing_result.type": "ExecutableQuery",
            "recognized_query_mode": "single",
            "expected_intent_or_profile": "investment_profile",
            "ast_generation_mode": "llm_ast_draft",
            "remote_query_allowed": "true",
            "llm_ast_draft_required": "true",
        }
    )
    result = {
        "answer": "这是一个很长的回答。" * 30,
        "v3": {
            "routing_result": {"type": "ExecutableQuery"},
            "recognized_query_mode": "single",
            "intent": "investment_profile",
            "ast_generation_mode": "llm_ast_draft",
            "remote_query_allowed": True,
            "llm_ast_draft_raw": "{}",
            "capability_status": "executable",
            "gate_status": "not_applicable",
            "provenance_diff": {
                "strict_pass": True,
                "semantic_additions": [],
                "semantic_overrides": [],
                "validator_additions_by_kind": {"semantic": []},
            },
        },
        "v3_ast": {"intent": "investment_profile"},
        "validated_ast": {"intent": "investment_profile"},
        "query_plan": {"collection": "tb_ths_etf_base"},
        "mongo_params": {"collection": "tb_ths_etf_base"},
        "result": {"success": True, "data": {}},
    }

    evaluated = evaluate_row(row, result)

    assert evaluated["answer"].endswith("这是一个很长的回答。")
    assert evaluated["display_answer"].endswith("...")
    assert len(evaluated["display_answer"]) < len(evaluated["answer"])


def test_v3_2_audit_preserves_brief_aligned_table_answers():
    from scripts.audit_v3_2_results import _brief_user_answer

    answer = "\n".join(
        [
            "| 基金代码 | 基金简称 | 基金规模 |",
            "| --- | --- | --- |",
            "| 513880 | 日经225ETF华安 | 24.92 亿元 |",
            "| 516300 | 中证1000ETF华泰柏瑞 | 0.90 亿元 |",
            "| 515920 | 智能消费ETF博时 | 0.98 亿元 |",
            "| 517990 | 沪港深医药ETF招商 | 0.39 亿元 |",
            "| 159623 | 成渝经济圈ETF博时 | 32.74 亿元 |",
            "| 588310 | 科创创业ETF方正富邦 | 0.42 亿元 |",
        ]
    )

    brief = _brief_user_answer(answer)

    assert "基金代码" in brief
    assert "---" not in brief
    assert "\n" in brief
    assert brief.endswith("...")


def test_v3_2_audit_scoped_only_counts_v3_2_required_rows_as_fail():
    from scripts.audit_v3_2_results import CoverageRow, evaluate_row

    row = CoverageRow(
        {
            "question_id": "二.8",
            "question": "510300近半年收益率和同类平均比怎么样",
            "routing_result.type": "UnsupportedQuery",
            "recognized_query_mode": "null",
            "expected_intent_or_profile": "unsupported_peer_average",
            "ast_generation_mode": "null",
            "remote_query_allowed": "false",
            "llm_ast_draft_required": "false",
            "release_scope": "v3_3_required",
        }
    )
    result = {
        "question": "510300近半年收益率和同类平均比怎么样",
        "answer": "不在 v3.2 能力范围",
        "v3": {
            "routing_result": {"type": "UnsupportedQuery"},
            "recognized_query_mode": "unsupported",
            "intent": None,
            "ast_generation_mode": None,
            "remote_query_allowed": False,
        },
    }

    evaluated = evaluate_row(row, result)

    assert evaluated["status"] == "SKIP"
    assert evaluated["display_answer"] == "不在 v3.2 能力范围"
