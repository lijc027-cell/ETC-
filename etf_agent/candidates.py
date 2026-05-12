from __future__ import annotations

from .dictionary import FieldMapping, mapping_lookup


KEYWORD_FIELDS = [
    (("是什么", "介绍", "基本信息", "概况"), [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_type_fund",
        "ths_fund_invest_type_fund",
        "ths_name_of_tracking_index_fund",
        "ths_fund_scale_fund",
        "ths_fund_establishment_date_fund",
        "ths_fund_supervisor_fund",
    ]),
    (("盘子", "规模", "多大", "资产规模"), ["ths_fund_scale_fund", "ths_current_mv_fund"]),
    (("跟踪", "跟的", "指数", "标的指数"), ["ths_tracking_index_code_fund", "ths_name_of_tracking_index_fund"]),
    (("管理费", "托管费", "费率", "贵不贵"), ["ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"]),
    (("基金经理", "谁在管", "管理人"), ["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"]),
    (("分红",), ["ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"]),
]

PERIOD_FIELDS = {
    "1w": ["ths_yeild_1w_fund", "ths_yeild_rank_1w_fund_origin", "ths_yeild_rank_1w_etf"],
    "1m": ["ths_yeild_1m_fund", "ths_yeild_rank_1m_fund_origin", "ths_yeild_rank_1m_etf"],
    "3m": ["ths_yeild_3m_fund", "ths_yeild_rank_3m_fund_origin", "ths_yeild_rank_3m_etf"],
    "6m": ["ths_yeild_6m_fund", "ths_yeild_rank_6m_fund_origin", "ths_yeild_rank_6m_etf"],
    "1y": ["ths_yeild_1y_fund", "ths_yeild_rank_1y_fund_origin", "ths_yeild_rank_1y_etf"],
    "2y": ["ths_yeild_2y_fund", "ths_yeild_rank_2y_fund_origin", "ths_yeild_rank_2y_etf"],
    "3y": ["ths_yeild_3y_fund", "ths_yeild_rank_3y_fund_origin", "ths_yeild_rank_3y_etf"],
    "5y": ["ths_yeild_5y_fund", "ths_yeild_rank_5y_fund_origin", "ths_yeild_rank_5y_etf"],
    "ytd": ["ths_yeild_ytd_fund", "ths_yeild_rank_ytd_fund_origin", "ths_yeild_rank_ytd_etf"],
    "std": ["ths_yeild_std_fund", "ths_yeild_rank_std_fund_origin", "ths_yeild_rank_std_etf"],
    "all": [
        "ths_yeild_1w_fund",
        "ths_yeild_1m_fund",
        "ths_yeild_3m_fund",
        "ths_yeild_6m_fund",
        "ths_yeild_1y_fund",
        "ths_yeild_2y_fund",
        "ths_yeild_3y_fund",
        "ths_yeild_5y_fund",
        "ths_yeild_ytd_fund",
        "ths_yeild_std_fund",
    ],
}


def enhance_candidates(
    question: str,
    entities: dict[str, str],
    mappings: list[FieldMapping],
    vector_results: list[dict],
) -> list[dict]:
    lookup = mapping_lookup(mappings)
    selected: dict[str, dict] = {}

    for field in _enhanced_fields(question, entities):
        item = lookup.get(f"tb_ths_etf_base.{field}")
        if item:
            selected[item.id] = _candidate(item, "enhanced")

    for result in vector_results:
        item = result["mapping"]
        if item.id in selected:
            selected[item.id]["score"] = result.get("score")
            continue
        selected[item.id] = _candidate(item, "vector", result.get("score"))

    return list(selected.values())


def _enhanced_fields(question: str, entities: dict[str, str]) -> list[str]:
    fields: list[str] = []
    for keywords, rule_fields in KEYWORD_FIELDS:
        if any(keyword in question for keyword in keywords):
            fields.extend(rule_fields)
    if any(word in question for word in ("表现", "收益率", "收益", "涨跌", "赚了", "回报", "各周期")):
        fields.extend(PERIOD_FIELDS[entities.get("period", "1y")])
    return _dedupe(fields)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _candidate(item: FieldMapping, source: str, score: float | None = None) -> dict:
    return {
        "id": item.id,
        "collection": item.collection,
        "field": item.field,
        "cn_name": item.cn_name,
        "type": item.type,
        "description": item.description,
        "section": item.section,
        "score": score,
        "source": source,
    }
