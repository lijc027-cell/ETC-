import json
from pathlib import Path

import pytest

from etf_agent.cache import build_cache_signature
from etf_agent.candidates import enhance_candidates
from etf_agent.dictionary import parse_data_dictionary
from etf_agent.entities import extract_entities
from etf_agent.formatter import format_answer
from etf_agent.llm import deterministic_plan, is_plan_schema_like
from etf_agent.name_resolver import resolve_fundcode_from_catalog
from etf_agent.retrieval import EMBEDDING_BATCH_SIZE
from etf_agent.plan import PlanValidationError, build_sql_like, validate_query_plan
from etf_agent.v3 import (
    build_v3_ast,
    build_v3_1_ast,
    classify_v3_query,
    extract_v3_1_entity_hints,
    extract_v3_test_questions,
)


ROOT = Path(__file__).resolve().parents[1]
DICTIONARY = ROOT / "references" / "data-dictionary.md"


def mappings():
    return parse_data_dictionary(DICTIONARY)


def test_parse_data_dictionary_extracts_all_collections_and_search_text():
    items = mappings()
    ids = {item.id for item in items}

    assert "tb_ths_etf_base.ths_fund_scale_fund" in ids
    assert "tb_ths_etf_report_quarter.ths_zcgnmc_fund" in ids
    assert "tb_ths_etf_report_year.ths_top_held_stock_code_fund" in ids

    scale = next(item for item in items if item.id == "tb_ths_etf_base.ths_fund_scale_fund")
    assert scale.collection == "tb_ths_etf_base"
    assert scale.field == "ths_fund_scale_fund"
    assert scale.cn_name == "基金规模"
    assert scale.type == "number"
    assert scale.description == "单位：元"
    assert scale.section == "规模与净值"
    assert scale.search_text == (
        "ETF字段 基金规模 单位：元 所属分组:规模与净值 "
        "集合:tb_ths_etf_base 字段:ths_fund_scale_fund"
    )


@pytest.mark.parametrize(
    ("question", "period"),
    [
        ("510300 近一周收益", "1w"),
        ("510300 近1月表现", "1m"),
        ("510300 近三月表现", "3m"),
        ("510300 近6月表现", "6m"),
        ("510300 最近一年表现", "1y"),
        ("510300 今年以来收益", "ytd"),
        ("510300 成立以来收益", "std"),
    ],
)
def test_extract_entities_fundcode_and_period(question, period):
    assert extract_entities(question) == {"fundcode": "510300", "period": period}


def test_extract_entities_requires_fundcode():
    with pytest.raises(ValueError, match="未识别到 6 位 ETF 基金代码"):
        extract_entities("沪深300 ETF 盘子有多大")


def test_enhance_candidates_adds_scale_fields_before_vector_candidates():
    items = mappings()
    vector_item = next(item for item in items if item.field == "ths_name_of_tracking_index_fund")

    candidates = enhance_candidates(
        "510300 盘子有多大",
        {"fundcode": "510300"},
        items,
        [{"mapping": vector_item, "score": 0.66}],
    )

    assert [candidate["field"] for candidate in candidates[:2]] == [
        "ths_fund_scale_fund",
        "ths_current_mv_fund",
    ]
    assert candidates[0]["source"] == "enhanced"
    assert candidates[-1]["field"] == "ths_name_of_tracking_index_fund"
    assert candidates[-1]["score"] == 0.66


def test_validate_query_plan_rejects_unsafe_filter_operator():
    items = mappings()
    plan = {
        "intent": "fund_scale",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": {"$ne": "510300"}},
        "projection": ["fundcode", "ths_fund_scale_fund"],
        "limit": 1,
        "answer_fields": [
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "yuan_to_100m"}
        ],
    }

    with pytest.raises(PlanValidationError, match="filter value 不允许 object 或 array"):
        validate_query_plan(plan, items, {"fundcode": "510300"}, [])


def test_validate_query_plan_rejects_unknown_projection_and_array_fields():
    items = mappings()
    candidate_ids = ["tb_ths_etf_base.ths_unknown_field"]
    unknown_plan = {
        "intent": "basic_info",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode", "ths_unknown_field"],
        "limit": 1,
        "answer_fields": [{"field": "ths_unknown_field", "label": "未知", "format": "plain"}],
    }

    with pytest.raises(PlanValidationError, match="未知字段"):
        validate_query_plan(unknown_plan, items, {"fundcode": "510300"}, candidate_ids)

    array_plan = {
        "intent": "manager",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode", "ths_manager"],
        "limit": 1,
        "answer_fields": [{"field": "ths_manager", "label": "基金经理详情", "format": "plain"}],
    }

    with pytest.raises(PlanValidationError, match="array/object 字段"):
        validate_query_plan(array_plan, items, {"fundcode": "510300"}, ["tb_ths_etf_base.ths_manager"])


def test_validate_query_plan_completes_intent_template_and_sql_like():
    items = mappings()
    plan = {
        "intent": "tracking_index",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode"],
        "limit": 1,
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    validated = validate_query_plan(plan, items, {"fundcode": "510300"}, [])

    assert validated["projection"] == [
        "fundcode",
        "ths_tracking_index_code_fund",
        "ths_name_of_tracking_index_fund",
    ]
    assert build_sql_like(validated) == (
        "SELECT fundcode, ths_tracking_index_code_fund, ths_name_of_tracking_index_fund\n"
        "FROM tb_ths_etf_base\n"
        "WHERE fundcode = '510300'\n"
        "LIMIT 1;"
    )


def test_template_completed_performance_fields_are_allowed_outside_candidates():
    items = mappings()
    plan = {
        "intent": "performance",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode"],
        "limit": 1,
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    validated = validate_query_plan(
        plan,
        items,
        {"fundcode": "510300", "period": "1y"},
        ["tb_ths_etf_base.fundcode"],
    )

    assert validated["projection"] == [
        "fundcode",
        "ths_yeild_1y_fund",
        "ths_yeild_rank_1y_fund_origin",
        "ths_yeild_rank_1y_etf",
    ]


def test_existing_template_fields_are_allowed_outside_candidates():
    items = mappings()
    plan = {
        "intent": "basic_info",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_name_of_tracking_index_fund",
            "ths_fund_scale_fund",
        ],
        "limit": 1,
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    validated = validate_query_plan(plan, items, {"fundcode": "510300"}, ["tb_ths_etf_base.fundcode"])

    assert "ths_fund_scale_fund" in validated["projection"]


def test_v1_rejects_non_base_collections_and_unknown_intents():
    items = mappings()
    yearly_plan = {
        "intent": "unknown",
        "collection": "tb_ths_etf_report_year",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode", "year_num"],
        "limit": 1,
        "answer_fields": [{"field": "year_num", "label": "年份", "format": "plain"}],
    }

    with pytest.raises(PlanValidationError, match="v1 暂不支持"):
        validate_query_plan(yearly_plan, items, {"fundcode": "510300"}, [])

    unknown_plan = {
        "intent": "unknown",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode"],
        "limit": 1,
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    with pytest.raises(PlanValidationError, match="v1 暂不支持"):
        validate_query_plan(unknown_plan, items, {"fundcode": "510300"}, [])


def test_qwen_intent_aliases_are_normalized_to_v1_intents():
    items = mappings()
    plan = {
        "intent": "fund_performance",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode", "ths_yeild_1y_fund"],
        "limit": 1,
        "answer_fields": [{"field": "ths_yeild_1y_fund", "label": "近1年收益率", "format": "percent"}],
    }

    validated = validate_query_plan(plan, items, {"fundcode": "510300", "period": "1y"}, [])

    assert validated["intent"] == "performance"


def test_qwen_fee_and_manager_alias_is_allowed():
    items = mappings()
    plan = {
        "intent": "fund_fee_and_manager",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510350"},
        "projection": [
            "fundcode",
            "ths_manage_fee_rate_fund",
            "ths_mandate_fee_rate_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
        ],
        "limit": 1,
        "answer_fields": [
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
            {"field": "ths_mandate_fee_rate_fund", "label": "托管费率", "format": "percent"},
            {"field": "ths_fund_manager_current_fund", "label": "基金经理(现任)", "format": "plain"},
            {"field": "ths_fund_supervisor_fund", "label": "基金管理人", "format": "plain"},
        ],
    }

    validated = validate_query_plan(plan, items, {"fundcode": "510350"}, [])

    assert validated["intent"] == "fee_and_manager"


@pytest.mark.parametrize(
    ("raw_intent", "period", "expected"),
    [
        ("yield_ytd", "ytd", "performance"),
        ("fund_yield", "1w", "performance"),
        ("fund_performance_rank", "1y", "performance"),
        ("fund_return_since_inception", "std", "performance"),
        ("fund_manager", None, "manager"),
        ("dividend_record", None, "dividend"),
        ("fund_dividend", None, "dividend"),
    ],
)
def test_qwen_intent_drift_is_normalized_to_v1_intents(raw_intent, period, expected):
    items = mappings()
    entities = {"fundcode": "510300"}
    if period:
        entities["period"] = period
    plan = {
        "intent": raw_intent,
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode"],
        "limit": 1,
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    validated = validate_query_plan(plan, items, entities, ["tb_ths_etf_base.fundcode"])

    assert validated["intent"] == expected


def test_unknown_intent_still_rejected_after_normalization():
    items = mappings()
    plan = {
        "intent": "market_quote",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode"],
        "limit": 1,
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    with pytest.raises(PlanValidationError, match="v1 暂不支持 intent"):
        validate_query_plan(plan, items, {"fundcode": "510300"}, ["tb_ths_etf_base.fundcode"])


def test_format_answer_uses_answer_fields_without_model_summary():
    plan = {
        "filter": {"fundcode": "510300"},
        "answer_fields": [
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "yuan_to_100m"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
        ],
    }
    result = {"success": True, "data": {"ths_fund_scale_fund": 12345678900, "ths_manage_fee_rate_fund": 0.5}}

    answer = format_answer(plan, result)

    assert answer == "510300 的基金规模为 123.46 亿元，管理费率为 0.50%。"


def test_format_answer_keeps_rank_origin_as_plain_text():
    plan = {
        "filter": {"fundcode": "510300"},
        "answer_fields": [
            {"field": "ths_yeild_1y_fund", "label": "近1年收益率", "format": "percent"},
            {"field": "ths_yeild_rank_1y_fund_origin", "label": "近1年同类排名", "format": "plain"},
            {"field": "ths_yeild_rank_1y_etf", "label": "近1年 ETF 排名", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "ths_yeild_1y_fund": 8.88,
            "ths_yeild_rank_1y_fund_origin": "100/500",
            "ths_yeild_rank_1y_etf": 12,
        },
    }

    answer = format_answer(plan, result)

    assert answer == "510300 的近1年收益率为 8.88%，近1年同类排名为 100/500，近1年 ETF 排名为 12。"


def test_format_answer_uses_latest_timeseries_value():
    plan = {
        "filter": {"fundcode": "510300"},
        "answer_fields": [
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "yuan_to_100m"},
        ],
    }
    result = {
        "success": True,
        "data": {
            "ths_fund_scale_fund": [
                {"value": 100000000, "btime": "2026-01-01"},
                {"value": 250000000, "btime": "2026-05-05"},
            ]
        },
    }

    answer = format_answer(plan, result)

    assert answer == "510300 的基金规模为 2.50 亿元（2026-05-05）。"


def test_compare_formatter_preserves_requested_fundcode_order():
    plan = {
        "filter": {"fundcode": {"$in": ["510300", "510500", "159919"]}},
        "output_style": "compare",
        "answer_fields": [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
        ],
    }
    result = {
        "success": True,
        "data": [
            {"fundcode": "510500", "ths_fund_extended_inner_short_name_fund": "中证500ETF"},
            {"fundcode": "159919", "ths_fund_extended_inner_short_name_fund": "沪深300ETF深市"},
            {"fundcode": "510300", "ths_fund_extended_inner_short_name_fund": "沪深300ETF"},
        ],
    }

    answer = format_answer(plan, result)

    assert answer.splitlines()[0] == "| 指标 | 510300 | 510500 | 159919 |"


@pytest.mark.parametrize("data", [None, [], {}])
def test_format_answer_reports_missing_etf_for_empty_results(data):
    plan = {
        "filter": {"fundcode": "000001"},
        "answer_fields": [{"field": "fundcode", "label": "基金代码", "format": "plain"}],
    }

    assert format_answer(plan, {"success": True, "data": data}) == "未在 ETF 数据库中找到代码 000001 对应的 ETF。"


def test_deterministic_performance_plan_formats_rank_fields_as_plain():
    items = mappings()
    candidates = enhance_candidates(
        "510300 近一年表现怎么样",
        {"fundcode": "510300", "period": "1y"},
        items,
        [],
    )

    plan = deterministic_plan("510300 近一年表现怎么样", {"fundcode": "510300", "period": "1y"}, candidates)

    formats = {item["field"]: item["format"] for item in plan["answer_fields"]}
    assert formats["ths_yeild_1y_fund"] == "percent"
    assert formats["ths_yeild_rank_1y_fund_origin"] == "plain"
    assert formats["ths_yeild_rank_1y_etf"] == "plain"


def test_cache_signature_changes_when_embedding_config_changes(tmp_path):
    dictionary = tmp_path / "data-dictionary.md"
    dictionary.write_text("abc", encoding="utf-8")

    first = build_cache_signature(dictionary, "text-embedding-v3", 1024, "https://dashscope.aliyuncs.com/compatible-mode/v1")
    second = build_cache_signature(dictionary, "other-model", 1024, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    assert first["dictionary_hash"] == second["dictionary_hash"]
    assert first != second


def test_embedding_batch_size_matches_dashscope_limit():
    assert EMBEDDING_BATCH_SIZE == 10


@pytest.mark.parametrize(
    ("question", "period"),
    [
        ("510300 今年收益", "ytd"),
        ("510300 近2年收益", "2y"),
        ("510300 近三年收益", "3y"),
        ("510300 近5年收益", "5y"),
        ("510300 各周期收益率", "all"),
    ],
)
def test_extract_entities_additional_periods(question, period):
    assert extract_entities(question)["period"] == period


def test_invalid_json_plan_has_stage_friendly_error():
    from etf_agent.llm import parse_plan_json

    with pytest.raises(ValueError, match="Qwen 返回非法 JSON"):
        parse_plan_json("```json\nnot-json\n```")


def test_plan_json_extracts_code_fence_with_prefix_text():
    from etf_agent.llm import parse_plan_json

    content = """好的，这是查询计划：
```json
{"intent": "fund_scale", "collection": "tb_ths_etf_base", "filter": {"fundcode": "510300"}, "projection": ["fundcode"], "limit": 1, "answer_fields": []}
```
"""

    assert parse_plan_json(content)["intent"] == "fund_scale"


def test_plan_schema_like_rejects_qwen_loose_answer_fields():
    loose_plan = {
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["ths_fund_scale_fund"],
        "limit": 1,
        "answer_fields": ["基金规模"],
        "format": "yuan_to_100m",
    }

    assert is_plan_schema_like(loose_plan) is False


def test_plan_schema_like_allows_extra_keys_for_validator_to_reject():
    loose_plan = {
        "intent": "fund_scale",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode"],
        "limit": 1,
        "answer_fields": [],
        "_comment": "extra",
    }

    assert is_plan_schema_like(loose_plan) is True


def test_non_template_field_requires_non_empty_candidates():
    items = mappings()
    plan = {
        "intent": "basic_info",
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": "510300"},
        "projection": ["fundcode", "ths_current_mv_fund"],
        "limit": 1,
        "answer_fields": [{"field": "ths_current_mv_fund", "label": "总市值", "format": "yuan_to_100m"}],
    }

    with pytest.raises(PlanValidationError, match="候选字段为空"):
        validate_query_plan(plan, items, {"fundcode": "510300"}, [])


def test_dry_run_semantic_query_returns_answer_and_debug_structure():
    from etf_agent import semantic_query

    result = semantic_query("510300 是什么", root=ROOT, dry_run=True)

    assert result["answer"].startswith("510300 的")
    assert result["entities"] == {"fundcode": "510300"}
    assert result["query_plan"]["collection"] == "tb_ths_etf_base"
    assert result["debug"]["stages"][0]["name"] == "dictionary_parse"


def test_name_resolver_matches_reversed_manager_and_index_keywords():
    catalog = [
        {
            "fundcode": "510350",
            "thscode": "510350.SH",
            "ths_fund_extended_inner_short_name_fund": "沪深300ETF工银",
            "ths_fund_supervisor_fund": "工银瑞信基金",
            "ths_name_of_tracking_index_fund": "沪深300指数",
            "ths_tracking_index_code_fund": "000300",
        },
        {
            "fundcode": "510330",
            "thscode": "510330.SH",
            "ths_fund_extended_inner_short_name_fund": "沪深300ETF华夏",
            "ths_fund_supervisor_fund": "华夏基金",
            "ths_name_of_tracking_index_fund": "沪深300指数",
            "ths_tracking_index_code_fund": "000300",
        },
    ]

    resolved = resolve_fundcode_from_catalog("工银沪深300ETF的费率和基金经理是什么", catalog)

    assert resolved["status"] == "matched"
    assert resolved["fundcode"] == "510350"
    assert resolved["matched_name"] == "沪深300ETF工银"
    assert resolved["matched_thscode"] == "510350.SH"


def test_name_resolver_returns_ambiguous_for_broad_index_name():
    catalog = [
        {"fundcode": "510350", "thscode": "510350.SH", "ths_fund_extended_inner_short_name_fund": "沪深300ETF工银", "ths_fund_supervisor_fund": "工银瑞信基金", "ths_name_of_tracking_index_fund": "沪深300指数"},
        {"fundcode": "510330", "thscode": "510330.SH", "ths_fund_extended_inner_short_name_fund": "沪深300ETF华夏", "ths_fund_supervisor_fund": "华夏基金", "ths_name_of_tracking_index_fund": "沪深300指数"},
    ]

    resolved = resolve_fundcode_from_catalog("沪深300ETF的费率是多少", catalog)

    assert resolved["status"] == "ambiguous"
    assert [item["fundcode"] for item in resolved["matches"]] == ["510350", "510330"]


def test_name_resolver_returns_not_found():
    resolved = resolve_fundcode_from_catalog("不存在ETF的费率是多少", [])

    assert resolved == {"status": "not_found", "matches": []}


def test_pipeline_resolves_name_from_catalog_in_dry_run():
    from etf_agent import semantic_query

    result = semantic_query("工银沪深300ETF的费率和基金经理是什么", root=ROOT, dry_run=True)

    assert result["entities"]["fundcode"] == "510350"
    assert result["entities"]["resolved_by"] == "name"
    assert result["entities"]["matched_name"] == "沪深300ETF工银"
    assert "ths_manage_fee_rate_fund" in result["query_plan"]["projection"]
    assert "ths_fund_manager_current_fund" in result["query_plan"]["projection"]


def test_pipeline_returns_ambiguous_without_query_plan():
    from etf_agent import semantic_query

    result = semantic_query("沪深300ETF的费率是多少", root=ROOT, dry_run=True)

    assert "error" in result
    assert "匹配到多只 ETF" in result["error"]
    assert result["matches"]
    assert all(stage["name"] != "query_plan_generation" for stage in result["debug"]["stages"])


@pytest.mark.parametrize(
    "question",
    [
        "510300是什么",
        "帮我查一下510500的基本信息",
        "159919这只基金跟踪什么指数",
        "510300今年的收益率是多少",
        "159919近1年收益，同类排名第几",
        "510500成立以来收益怎么样",
        "帮我查510300各周期的收益率",
        "510300的基金经理是谁",
        "510300有没有分红记录",
        "159919的分红情况",
        "000001有这只ETF吗",
        "510300近一周收益",
    ],
)
def test_v1_acceptance_questions_pass_in_dry_run(question):
    from etf_agent import semantic_query

    result = semantic_query(question, root=ROOT, dry_run=True)

    assert "error" not in result
    assert result["answer"]
    assert result["query_plan"]["collection"] == "tb_ths_etf_base"
    assert result["entities"]["fundcode"]
    assert result["debug"]["stages"]


@pytest.mark.parametrize(
    "question",
    [
        "510300的持仓有哪些",
        "510300重仓行业是什么",
        "510300季报数据",
        "510300年报数据",
        "帮我找规模最大的ETF",
        "筛选收益率最高的ETF",
        "510300和510500对比一下",
        "510300实时行情",
        "有没有名字叫人工智能的ETF",
    ],
)
def test_out_of_scope_questions_remain_rejected(question):
    from etf_agent import semantic_query

    result = semantic_query(question, root=ROOT, dry_run=True)

    assert "error" in result


@pytest.mark.parametrize(
    ("question", "expected_mode", "expected_intent"),
    [
        ("510300是什么", "single", "basic_info"),
        ("510300的基金经理是谁", "single", "manager"),
        ("帮我查510300的实时行情", "deny", None),
        ("510300的持仓有哪些", "unsupported", None),
    ],
)
def test_v3_classification_covers_v3_0_questions(question, expected_mode, expected_intent):
    entities = {"fundcode": "510300"}
    if "实时" in question:
        entities = {"fundcode": "510300"}

    result = classify_v3_query(question, entities, [])

    assert result["recognized_query_mode"] == expected_mode
    assert result.get("intent") == expected_intent


def test_v3_ast_builds_single_query_shape_for_v1_baseline():
    entities = {"fundcode": "510300"}
    ast = build_v3_ast("basic_info", entities)

    assert ast == {
        "intent": "basic_info",
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
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_name_of_tracking_index_fund", "label": "跟踪指数名称", "format": "plain"},
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
        ],
        "report_period": None,
        "expand": None,
    }


def test_answer_md_exists_and_contains_v3_0_base_questions():
    answer_md = ROOT / "answer" / "test3.0-results.md"
    assert answer_md.exists()
    text = answer_md.read_text(encoding="utf-8")
    assert "v3.0" in text
    assert "510300是什么" in text


def test_semantic_query_v3_dry_run_has_v3_ast_and_amount_formatting():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("510300是什么", root=ROOT, dry_run=True)

    assert result["v3"]["recognized_query_mode"] == "single"
    assert result["v3_ast"]["intent"] == "basic_info"
    assert result["answer"] == "510300 的基金简称为 沪深300ETF，跟踪指数名称为 沪深300指数，基金规模为 123.46 亿元。"


def test_semantic_query_v3_resolves_chinese_name_in_dry_run():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("工银沪深300ETF的费率和基金经理是什么", root=ROOT, dry_run=True)

    assert result["entities"]["fundcode"] == "510350"
    assert result["v3_ast"]["intent"] == "fee_and_manager"
    assert "510350 的管理费率为 0.50%" in result["answer"]


def test_semantic_query_v3_returns_clarification_for_ambiguous_name_in_dry_run():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("沪深300ETF的费率是多少", root=ROOT, dry_run=True)

    assert result["v3"]["recognized_query_mode"] == "clarify"
    assert "匹配到多只 ETF" in result["answer"]
    assert result["v3"]["type"] == "ClarificationRequired"
    assert len(result["v3"]["options"]) > 1


def test_v3_performance_fields_do_not_include_numeric_fund_rank():
    ast = build_v3_ast("performance", {"fundcode": "510300", "period": "2y"})

    assert "ths_yeild_rank_2y_fund" not in ast["select"]
    assert all(field["field"] != "ths_yeild_rank_2y_fund" for field in ast["answer_fields"])
    assert "ths_yeild_rank_2y_fund_origin" in ast["select"]
    assert "ths_yeild_rank_2y_etf" in ast["select"]


def test_semantic_query_v3_does_not_deny_v3_0_net_value_or_etf_rank_questions():
    from etf_agent.v3 import _lexical_classify

    for question in ("510300近2年ETF排第几", "510300最新净值是多少", "510300净值增长率是多少"):
        classification = _lexical_classify(question, {"fundcode": "510300"}, [])
        assert classification["recognized_query_mode"] == "single"


def test_semantic_query_v3_empty_result_formats_not_found():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("000001有这只ETF吗", root=ROOT, dry_run=True)

    assert result["answer"] == "未在 ETF 数据库中找到代码 000001 对应的 ETF。"


def test_semantic_query_v3_denies_investment_advice_before_embedding():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("510300能买吗", root=ROOT, dry_run=True)

    assert result["v3"]["recognized_query_mode"] == "deny"
    assert "投资建议" in result["answer"]


def test_semantic_query_v3_recognizes_three_month_period_and_rank_label():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("510300近3个月涨了多少", root=ROOT, dry_run=True)

    assert result["entities"]["period"] == "3m"
    assert "ths_yeild_3m_fund" in result["v3_ast"]["select"]
    assert "近3月同类排名" in result["answer"]


@pytest.mark.parametrize(
    ("question", "expected_field", "expected_label"),
    [
        ("510300总市值多少", "ths_current_mv_fund", "总市值"),
        ("510300最新净值是多少", "ths_unit_nv_fund", "单位净值"),
        ("510300的份额有多少", "ths_fund_shares_fund", "基金份额"),
        ("510300的净值增长率是多少", "ths_unit_nvg_rate_fund", "单位净值增长率"),
    ],
)
def test_semantic_query_v3_fund_scale_subfields(question, expected_field, expected_label):
    from etf_agent import semantic_query_v3

    result = semantic_query_v3(question, root=ROOT, dry_run=True)

    assert result["v3_ast"]["intent"] == "fund_scale"
    assert expected_field in result["v3_ast"]["select"]
    assert result["v3_ast"]["answer_fields"][1]["field"] == expected_field
    assert result["v3_ast"]["answer_fields"][1]["label"] == expected_label


@pytest.mark.parametrize(
    ("question", "expected_mode"),
    [
        ("帮我找沪深300相关的ETF", "search"),
        ("找规模大于10亿的ETF", "filter"),
        ("成立以来收益最好的沪深300ETF是哪只", "filter"),
        ("近1年收益率超过20%的ETF", "filter"),
        ("对比510300、510500和159919", "compare"),
        ("股票型ETF里今年收益最高的5只是哪些？对比一下", "filter"),
        ("512880和510300哪个更好", "deny"),
    ],
)
def test_v3_1_classification_recognizes_search_filter_compare(question, expected_mode):
    result = classify_v3_query(question, {}, [])

    assert result["recognized_query_mode"] == expected_mode


@pytest.mark.parametrize(
    ("question", "expected_mode"),
    [
        ("低成本的沪深300产品都有哪些", "filter"),
        ("便宜一点的沪深300产品", "filter"),
        ("科创板50相关产品", "search"),
        ("偏债的场内基金有哪些", "filter"),
        ("510300 510500 159919放一起看看", "compare"),
        ("512880和510300谁费用更省", "compare"),
        ("沪深300产品里回报靠前的", "filter"),
        ("规模不小于100亿的产品", "filter"),
    ],
)
def test_v3_1_classification_recognizes_agent_paraphrases(question, expected_mode):
    result = classify_v3_query(question, {}, [])

    assert result["recognized_query_mode"] == expected_mode


def test_v3_1_agent_paraphrase_entity_hints():
    low_cost = extract_v3_1_entity_hints("低成本的沪深300产品都有哪些")
    bond = extract_v3_1_entity_hints("偏债的场内基金有哪些")
    min_scale = extract_v3_1_entity_hints("规模不小于100亿的产品")

    assert {"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "沪深300指数", "raw_value": "沪深300"} in low_cost["filters"]
    assert low_cost["order_by"] == {"field": "ths_manage_fee_rate_fund", "direction": "asc"}
    assert {"field": "ths_fund_invest_type_fund", "op": "eq", "value": "债券型"} in bond["filters"]
    assert {"field": "ths_fund_scale_fund", "op": "gte", "value": 10000000000} in min_scale["filters"]


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("159919这只基金跟踪什么指数", "tracking_index"),
        ("159919近1年收益，同类排名第几", "performance"),
        ("510300近5年收益率是多少，排名如何", "performance"),
    ],
)
def test_v3_1_does_not_steal_single_fund_questions(question, expected_intent):
    result = classify_v3_query(question, {}, [])

    assert result["recognized_query_mode"] == "single"
    assert result["intent"] == expected_intent


def test_v3_1_entity_hints_extract_search_filter_compare_signals():
    search = extract_v3_1_entity_hints("有没有名字里带医药的ETF")
    scale_filter = extract_v3_1_entity_hints("找规模大于10亿的ETF")
    compare = extract_v3_1_entity_hints("对比510300、510500和159919")

    assert search["search_keyword"] == "医药"
    assert scale_filter["filters"] == [
        {"field": "ths_fund_scale_fund", "op": "gt", "value": 1000000000}
    ]
    assert compare["fundcodes"] == ["510300", "510500", "159919"]


def test_v3_1_search_keyword_strips_trailing_structural_particle():
    hints = extract_v3_1_entity_hints('有没有ETF名字里带"红利"的')

    assert hints["search_keyword"] == "红利"


def test_v3_1_filter_extracts_tracking_index_before_de_particle():
    hints = extract_v3_1_entity_hints("对比所有跟踪沪深300的前5只ETF，看收益和费率")

    assert {"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "沪深300", "raw_value": "沪深300"} in hints["filters"]


def test_v3_1_filter_ast_projects_where_only_compare_field():
    hints = extract_v3_1_entity_hints("近1年收益率超过20%的ETF")
    ast = build_v3_1_ast("filter", hints, "近1年收益率超过20%的ETF")

    assert "ths_yeild_1y_fund" in ast["select"]
    assert {"field": "ths_yeild_1y_fund", "op": "gt", "value": 20} in ast["where"]
    assert {"field": "ths_yeild_1y_fund", "label": "近1年收益率", "format": "percent"} in ast["answer_fields"]


def test_v3_1_resolves_tracking_index_alias_to_catalog_value_in_dry_run():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("我想找跟踪科创50的ETF", root=ROOT, dry_run=True)

    assert result["v3"]["recognized_query_mode"] == "filter"
    assert {"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "上证科创板50成份指数"} in result["v3_ast"]["where"]


def test_index_catalog_resolves_alias_to_real_index_name():
    from etf_agent.index_catalog import resolve_index_name_from_catalog

    catalog = [
        {
            "ths_name_of_tracking_index_fund": "上证科创板50成份指数",
            "ths_tracking_index_code_fund": "000688",
        }
    ]

    assert resolve_index_name_from_catalog("科创50", catalog) == {
        "status": "matched",
        "value": "上证科创板50成份指数",
        "matches": [{"name": "上证科创板50成份指数", "code": "000688"}],
    }


def test_build_v3_1_search_ast_uses_contains_and_fixed_list_columns():
    hints = extract_v3_1_entity_hints("搜索中证500")
    ast = build_v3_1_ast("search", hints, "搜索中证500")

    assert ast["intent"] == "search"
    assert ast["output_style"] == "list"
    assert ast["where"] == [{"field": "__search_text__", "op": "contains", "value": "中证500"}]
    assert ast["select"] == [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
    ]


def test_build_v3_1_filter_ast_extracts_limit_order_and_filters():
    hints = extract_v3_1_entity_hints("找上交所规模前10的ETF")
    ast = build_v3_1_ast("filter", hints, "找上交所规模前10的ETF")

    assert ast["intent"] == "filter"
    assert ast["where"] == [{"field": "ths_fund_listed_exchange_fund", "op": "eq", "value": "上交所"}]
    assert ast["order_by"] == {"field": "ths_fund_scale_fund", "direction": "desc"}
    assert ast["limit"] == 10
    assert ast["output_style"] == "list"


def test_build_v3_1_compare_ast_uses_fundcode_in_and_fixed_columns():
    hints = extract_v3_1_entity_hints("对比510300、510500和159919")
    ast = build_v3_1_ast("compare", hints, "对比510300、510500和159919")

    assert ast["intent"] == "compare"
    assert ast["where"] == [{"field": "fundcode", "op": "in", "value": ["510300", "510500", "159919"]}]
    assert ast["output_style"] == "compare"
    assert ast["limit"] == 10
    assert len(ast["select"]) == 8


def test_semantic_query_v3_1_dry_run_formats_search_filter_and_compare():
    from etf_agent import semantic_query_v3

    search = semantic_query_v3("帮我找沪深300相关的ETF", root=ROOT, dry_run=True)
    filtered = semantic_query_v3("找规模大于10亿的ETF", root=ROOT, dry_run=True)
    compare = semantic_query_v3("对比510300、510500和159919", root=ROOT, dry_run=True)

    assert search["v3"]["recognized_query_mode"] == "search"
    assert "| 基金代码 | 基金简称 | 基金规模 | 管理费率 |" in search["answer"]
    assert filtered["v3"]["recognized_query_mode"] == "filter"
    assert filtered["v3_ast"]["where"][0]["field"] == "ths_fund_scale_fund"
    assert compare["v3"]["recognized_query_mode"] == "compare"
    assert "| 指标 | 510300 | 510500 | 159919 |" in compare["answer"]


def test_semantic_query_v3_1_compare_reports_missing_codes_in_dry_run():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("对比510300和000000", root=ROOT, dry_run=True)

    assert result["v3"]["recognized_query_mode"] == "compare"
    assert "| 指标 | 510300 |" in result["answer"]
    assert "缺失代码：000000" in result["answer"]


def test_semantic_query_v3_1_filter_sort_uses_stable_tiebreakers():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("哪些ETF管理费率最低", root=ROOT, dry_run=True)

    assert result["query_plan"]["sort"] == [
        ["ths_manage_fee_rate_fund", 1],
        ["ths_fund_scale_fund", -1],
        ["fundcode", 1],
    ]


def test_remote_runner_sort_documents_uses_all_sort_fields():
    from etf_agent.remote import RUNNER

    assert "sort_spec[0]" not in RUNNER
    assert "for field, direction in reversed(sort_spec)" in RUNNER


def test_extract_v3_test_questions_splits_v3_0_and_v3_1_scope():
    extracted = extract_v3_test_questions(ROOT / "etf-query-test-questions.md")

    v3_0_questions = {item["question"] for item in extracted if item["phase"] == "v3.0"}
    v3_1_questions = {item["question"] for item in extracted if item["phase"] == "v3.1"}
    excluded_questions = {item["question"] for item in extracted if item["phase"] == "excluded"}

    assert "510300是什么" in v3_0_questions
    assert "510300最新净值是多少" in v3_0_questions
    assert "帮我找沪深300相关的ETF" in v3_1_questions
    assert "成立以来收益最好的沪深300ETF是哪只" in v3_1_questions
    assert "找规模大于10亿的ETF" in v3_1_questions
    assert "对比510300、510500和159919" in v3_1_questions
    assert "对比510300和000000" in v3_1_questions
    assert "510300前十大重仓股是什么" in excluded_questions


def test_cli_print_report_handles_v3_1_composite_plan(capsys):
    from etf_agent import semantic_query_v3
    from etf_agent_demo import print_report

    output = semantic_query_v3("股票型ETF里今年收益最高的5只是哪些？对比一下", root=ROOT, dry_run=True)

    print_report(output, verbose=True)

    captured = capsys.readouterr()
    assert "查询步骤 1" in captured.out
    assert "查询步骤 2" in captured.out


def test_v3_1_filter_to_compare_marks_composite_route():
    from etf_agent import semantic_query_v3

    result = semantic_query_v3("股票型ETF里今年收益最高的5只是哪些？对比一下", root=ROOT, dry_run=True)

    assert result["v3"]["recognized_query_mode"] == "composite"
    assert result["v3"]["intent"] == "filter_to_compare"
    assert result["v3"]["steps"] == [
        {"recognized_query_mode": "filter", "intent": "filter"},
        {"recognized_query_mode": "compare", "intent": "compare"},
    ]
    assert "steps" in result["query_plan"]


def test_cli_default_prints_user_display_without_debug_sections(capsys):
    from etf_agent import semantic_query_v3
    from etf_agent_demo import print_report

    output = semantic_query_v3("510300是什么", root=ROOT, dry_run=True)

    print_report(output)

    captured = capsys.readouterr()
    assert "最终简短回答" in captured.out
    assert "关键查询信息" not in captured.out
    assert "v3 AST" not in captured.out


def test_cli_v3_verbose_search_does_not_require_v1_debug_fields(capsys):
    from etf_agent import semantic_query_v3
    from etf_agent_demo import print_report

    output = semantic_query_v3("搜索中证500", root=ROOT, dry_run=True)

    print_report(output, verbose=True)

    captured = capsys.readouterr()
    assert "v3 AST" in captured.out
    assert "查询计划" in captured.out
    assert "远端数据库结果" in captured.out
    assert "向量召回候选" not in captured.out


def test_v3_1_result_generator_defaults_to_real_remote_mode():
    script = (ROOT / "scripts" / "generate_v3_1_results.py").read_text(encoding="utf-8")

    assert "dry_run=True" not in script
    assert "no_llm=True" in script
    assert "远端真实 MongoDB" in script
    assert "OUT_JSON" in script
    assert "### Q" in script
    assert "_inline(" not in script


def test_v3_1_result_generator_evaluates_expected_failures():
    from scripts.generate_v3_1_results import evaluate_result

    result = {
        "answer": "未找到符合条件的 ETF。",
        "v3": {"recognized_query_mode": "filter", "intent": "filter"},
    }

    status, reason = evaluate_result("近1年收益率超过20%的ETF", result)

    assert status == "FAIL"
    assert "不应包含：未找到符合条件的 ETF" in reason


def test_audit_v3_reference_comparison_detects_empty_model_result():
    from scripts.audit_v3_results import compare_audit_case

    model = {
        "answer": "未找到符合条件的 ETF。",
        "v3": {"recognized_query_mode": "filter", "intent": "filter"},
        "query_plan": {"collection": "tb_ths_etf_base", "filter": {"ths_yeild_1y_fund": {"$gt": 20}}, "sort": []},
        "result": {"success": True, "data": []},
    }
    reference = {"data": [{"fundcode": "510300", "ths_yeild_1y_fund": 31.27}]}

    audited = compare_audit_case(
        question="近1年收益率超过20%的ETF",
        expected={"route": ("filter", "filter"), "filter": {"ths_yeild_1y_fund": {"$gt": 20}}},
        model=model,
        reference=reference,
    )

    assert audited["status"] == "FAIL"
    assert "model returned empty" in audited["reason"]


def test_agent_result_evaluator_rejects_forbidden_fields():
    from scripts.generate_v3_1_agent_results import evaluate_agent_result

    result = {
        "answer": "ok",
        "v3": {"recognized_query_mode": "filter", "intent": "filter"},
        "query_plan": {"collection": "tb_ths_etf_base", "filter": {}, "projection": ["fundcode", "made_up_field"]},
        "result": {"success": True, "data": [{"fundcode": "510300"}]},
    }

    status, reason = evaluate_agent_result("低成本的沪深300产品都有哪些", result)

    assert status == "FAIL"
    assert "forbidden field" in reason


def test_answer_directory_keeps_only_result_markdown_files():
    files = sorted(path.name for path in (ROOT / "answer").iterdir() if path.is_file())

    assert files == [
        "test3.0-results.md",
        "test3.1-agent-results.md",
        "test3.1-results.md",
    ]
