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
