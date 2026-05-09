from __future__ import annotations

import re
from typing import Any

from .candidates import PERIOD_FIELDS
from .capability_registry import COMPARE_FIELDS, LIST_BASELINE_FIELDS, field_meta, get_selection_context


IDENTITY_CONTEXT_FIELDS = {"fundcode", "ths_fund_extended_inner_short_name_fund"}


def build_generation_bundle(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
    phase: str = "v3.2",
) -> dict[str, Any]:
    selection_context = get_selection_context(query_mode, intent, phase=phase)
    evidence = _build_evidence(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints)
    expectations = _build_expectations(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints)

    return {
        "llm_context": {
            "capability": {
                "recognized_query_mode": query_mode,
                "intent": intent,
                "from": selection_context["collection"],
                "output_style": selection_context["output_style"],
                "field_profile": selection_context["field_profile"],
            },
            "selectable_fields": _field_cards(selection_context["selectable_fields"]),
            "where_constraints": {
                "field_operators": selection_context["field_operators"],
                "value_schemas": selection_context["value_schemas"],
                "normalizers": selection_context["normalizers"],
                "gates": selection_context["gates"],
            },
            "sortable_fields": selection_context["sortable_fields"],
            "answer_field_formats": selection_context["allowed_formats"],
            "identity_context_fields": [
                field for field in selection_context["baseline_answer_fields"] if field in IDENTITY_CONTEXT_FIELDS
            ],
            "limit_policy": _limit_policy(query_mode),
            "llm_draft_evidence": evidence,
            "strict_validation_contract": _strict_validation_contract(expectations),
        },
        "selection_context": selection_context,
        "validator_expectations": expectations,
    }


def _strict_validation_contract(expectations: dict[str, Any]) -> dict[str, Any]:
    return {
        "required_select_fields": list(expectations.get("required_select_fields") or []),
        "required_answer_fields": list(expectations.get("required_select_fields") or []),
        "expected_where": [dict(item) for item in expectations.get("expected_where") or []],
        "expected_order_by": expectations.get("expected_order_by"),
        "expected_limit": expectations.get("expected_limit"),
        "expected_sub_intents": list(expectations.get("expected_sub_intents") or []),
    }


def _field_cards(fields: list[str]) -> list[dict[str, str]]:
    cards = []
    for field in fields:
        label, fmt = field_meta(field)
        cards.append({"field": field, "label": label, "format": fmt})
    return cards


def _limit_policy(query_mode: str) -> dict[str, int]:
    if query_mode == "search":
        return {"default": 20, "max": 50}
    if query_mode == "compare":
        return {"default": 10, "max": 10}
    if query_mode == "filter":
        return {"default": 10, "max": 50}
    return {"default": 1, "max": 1}


def _build_evidence(question: str, *, query_mode: str, intent: str, entity_hints: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": question,
        "fundcodes": list(entity_hints.get("fundcodes") or []),
        "period": entity_hints.get("period"),
        "search_keyword_evidence": _search_keyword_evidence(question, entity_hints),
        "field_cues": _field_cues(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "numeric_evidence": _numeric_evidence(question),
        "date_evidence": _date_evidence(question),
        "limit_evidence": _limit_evidence(question, entity_hints),
        "sort_evidence": _sort_evidence(question),
        "query_mode": query_mode,
    }


def _build_expectations(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
) -> dict[str, Any]:
    return {
        "required_select_fields": _required_select_fields(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "display_default_fields": _display_default_fields(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "expected_where": _expected_where(query_mode, entity_hints),
        "expected_order_by": entity_hints.get("order_by"),
        "expected_limit": entity_hints.get("limit_hint"),
        "expected_sub_intents": _expected_sub_intents(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "semantic_field_labels": _semantic_field_labels(),
    }


def _required_select_fields(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
) -> list[str]:
    if query_mode == "search":
        return []
    if query_mode == "filter":
        fields = []
        order_by = entity_hints.get("order_by")
        if order_by and order_by["field"] not in fields:
            fields.append(order_by["field"])
        return fields
    if query_mode == "compare":
        return _compare_fields(question, entity_hints.get("period") or "1y")
    if intent == "basic_info":
        return [
            "ths_fund_extended_inner_short_name_fund",
            "ths_name_of_tracking_index_fund",
            "ths_fund_scale_fund",
        ]
    if intent == "composite_single":
        return _composite_single_required_fields(question)
    if intent == "basic_info_extended":
        return _basic_info_extended_fields(question)
    if intent == "investment_profile":
        return _investment_profile_fields(question)
    if intent == "fund_scale":
        return [_fund_scale_field(question)]
    if intent == "tracking_index":
        return ["ths_tracking_index_code_fund", "ths_name_of_tracking_index_fund"]
    if intent == "fee":
        return ["ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"]
    if intent == "manager":
        return ["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"]
    if intent == "fee_and_manager":
        return [
            "ths_manage_fee_rate_fund",
            "ths_mandate_fee_rate_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
        ]
    if intent == "dividend":
        if "几次" in question or "多少次" in question:
            return ["ths_accum_dividend_times_fund"]
        if "多少" in question or "总额" in question or "累计" in question:
            return ["ths_accum_dividend_total_amt_fund"]
        return ["ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"]
    if intent == "performance":
        period = entity_hints.get("period") or "1y"
        if period == "all":
            return list(PERIOD_FIELDS["all"])
        return _performance_required_fields(question, period)
    if intent == "composite_single":
        return [
            *PERIOD_FIELDS["std"],
            "ths_accum_dividend_total_amt_fund",
            "ths_accum_dividend_times_fund",
        ]
    return []


def _display_default_fields(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
) -> list[str]:
    if query_mode in {"search", "filter"}:
        return list(LIST_BASELINE_FIELDS)
    if intent == "manager":
        return ["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"]
    if intent == "dividend":
        return ["ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"]
    if intent == "performance":
        period = entity_hints.get("period") or "1y"
        if period == "all":
            return []
        return list(PERIOD_FIELDS.get(period, PERIOD_FIELDS["1y"])[1:])
    return []


def _expected_where(query_mode: str, entity_hints: dict[str, Any]) -> list[dict[str, Any]]:
    fundcodes = [str(item) for item in entity_hints.get("fundcodes") or [] if item]
    if query_mode == "single" and fundcodes:
        return [{"field": "fundcode", "op": "eq", "value": fundcodes[0]}]
    if query_mode == "search":
        return [{"field": "__search_text__", "op": "contains", "value": str(entity_hints.get("search_keyword") or "")}]
    if query_mode == "filter":
        return [dict(item) for item in entity_hints.get("filters") or []]
    if query_mode == "compare" and len(fundcodes) >= 2:
        return [{"field": "fundcode", "op": "in", "value": fundcodes[:10]}]
    return []


def _performance_required_fields(question: str, period: str) -> list[str]:
    fields = PERIOD_FIELDS.get(period, PERIOD_FIELDS["1y"])
    yield_field = fields[0]
    rank_fields = fields[1:]

    wants_rank = any(word in question for word in ("排名", "排第几", "排多少", "第几"))
    wants_yield = any(word in question for word in ("收益率", "收益", "表现", "回报", "涨", "跌", "涨跌", "赚了"))
    if not wants_rank:
        return [yield_field]

    selected_rank_fields = []
    if "同类" in question:
        selected_rank_fields.append(rank_fields[0])
    if "ETF" in question or "etf" in question.lower():
        selected_rank_fields.append(rank_fields[1])
    if not selected_rank_fields:
        selected_rank_fields.extend(rank_fields)

    result = [yield_field] if wants_yield else []
    result.extend(selected_rank_fields)
    return list(dict.fromkeys(result))


def _basic_info_extended_fields(question: str) -> list[str]:
    fields = []
    if "成立" in question:
        fields.append("ths_fund_establishment_date_fund")
    if "上市" in question:
        fields.append("ths_fund_listed_exchange_fund")
    if "业绩比较基准" in question or "比较基准" in question:
        fields.append("ths_perf_comparative_benchmark_fund")
    if "申购" in question or "赎回" in question or "申赎" in question:
        fields.append("ths_pur_and_redemp_status_fund")
    if "联接" in question:
        fields.append("ths_etf_to_code_fund")
    return fields


def _investment_profile_fields(question: str) -> list[str]:
    fields = []
    if "投资目标" in question or "目标" in question:
        fields.append("ths_invest_objective_fund")
    if "投资范围" in question or "范围" in question:
        fields.append("ths_invest_socpe_fund")
    if "投资理念" in question or "理念" in question:
        fields.append("ths_invest_philosophy_fund")
    if "投资策略" in question or "策略" in question:
        fields.append("ths_invest_strategy_fund")
    if "风险收益特征" in question or "风险" in question:
        fields.append("ths_risk_return_characteristics_fund")
    return fields


def _expected_sub_intents(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
) -> list[str]:
    if intent != "composite_single":
        return []
    sub_intents = []
    if "收益" in question or "排名" in question or "涨" in question or "跌" in question:
        sub_intents.append("performance")
    if "管理人" in question or "基金经理" in question:
        sub_intents.append("manager")
    if "申赎" in question or "申购" in question or "赎回" in question or "联接" in question:
        sub_intents.append("basic_info_extended")
    if "分红" in question or "分过红" in question:
        sub_intents.append("dividend")
    return list(dict.fromkeys(sub_intents))


def _composite_single_required_fields(question: str) -> list[str]:
    fields = ["fundcode", "ths_fund_extended_inner_short_name_fund"]
    if "收益" in question or "排名" in question or "涨" in question or "跌" in question:
        fields.extend(_performance_required_fields(question, "std"))
    if "管理人" in question or "基金经理" in question:
        fields.extend(["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"])
    if "申赎" in question or "申购" in question or "赎回" in question:
        fields.append("ths_pur_and_redemp_status_fund")
    if "联接" in question:
        fields.append("ths_etf_to_code_fund")
    if ("成立" in question and "成立以来" not in question) or "上市" in question or "业绩比较基准" in question:
        fields.extend(["ths_fund_establishment_date_fund", "ths_fund_listed_exchange_fund", "ths_perf_comparative_benchmark_fund"])
    if "投资目标" in question or "投资范围" in question or "投资理念" in question or "投资策略" in question or "风险收益特征" in question:
        fields.extend([
            "ths_invest_objective_fund",
            "ths_invest_socpe_fund",
            "ths_invest_philosophy_fund",
            "ths_invest_strategy_fund",
            "ths_risk_return_characteristics_fund",
        ])
    if "分红" in question or "分过红" in question:
        fields.extend(["ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"])
    return list(dict.fromkeys(fields))


def _compare_fields(question: str, period: str) -> list[str]:
    fields = ["fundcode", "ths_fund_extended_inner_short_name_fund"]
    if not any(word in question for word in ("规模", "费率", "收益", "收益率")):
        return list(COMPARE_FIELDS)
    if "规模" in question:
        fields.append("ths_fund_scale_fund")
    if "费率" in question or "费用" in question:
        fields.extend(["ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"])
    if "收益" in question or "收益率" in question:
        fields.append(f"ths_yeild_{period}_fund")
    return list(dict.fromkeys(fields))


def _fund_scale_field(question: str) -> str:
    if "净值增长率" in question:
        return "ths_unit_nvg_rate_fund"
    if "净值" in question:
        return "ths_unit_nv_fund"
    if "份额" in question:
        return "ths_fund_shares_fund"
    if "总市值" in question or "市值" in question:
        return "ths_current_mv_fund"
    return "ths_fund_scale_fund"


def _field_cues(question: str, *, query_mode: str, intent: str, entity_hints: dict[str, Any]) -> list[dict[str, str]]:
    return [{"text": _label_for_field(field), "candidate_field": field} for field in _required_select_fields(
        question,
        query_mode=query_mode,
        intent=intent,
        entity_hints=entity_hints,
    )]


def _search_keyword_evidence(question: str, entity_hints: dict[str, Any]) -> dict[str, str]:
    keyword = str(entity_hints.get("search_keyword") or "")
    return {"raw_question": question, "keyword": keyword}


def _numeric_evidence(question: str) -> list[dict[str, Any]]:
    evidence = []
    for match in re.finditer(r"([0-9.]+)\s*(亿|%)", question):
        raw_value, unit = match.groups()
        value = float(raw_value)
        if unit == "亿":
            value *= 100000000
        evidence.append({"raw": match.group(0), "value": int(value) if value.is_integer() else value, "unit": unit})
    return evidence


def _date_evidence(question: str) -> list[dict[str, str]]:
    return [{"raw": f"{year}年", "start": f"{year}-01-01", "end": f"{year}-12-31"} for year in re.findall(r"(20[0-9]{2})年", question)]


def _limit_evidence(question: str, entity_hints: dict[str, Any]) -> dict[str, Any]:
    return {"raw_question": question, "limit_hint": entity_hints.get("limit_hint")}


def _sort_evidence(question: str) -> dict[str, str]:
    return {"raw_question": question}


def _semantic_field_labels() -> dict[str, str]:
    return {field: field_meta(field)[0] for field in _all_known_semantic_fields()}


def _all_known_semantic_fields() -> list[str]:
    return list(
        dict.fromkeys(
            [
                *LIST_BASELINE_FIELDS,
                *COMPARE_FIELDS,
                *PERIOD_FIELDS["all"],
                "ths_fund_establishment_date_fund",
                "ths_fund_listed_exchange_fund",
                "ths_perf_comparative_benchmark_fund",
                "ths_pur_and_redemp_status_fund",
                "ths_etf_to_code_fund",
                "ths_invest_objective_fund",
                "ths_invest_socpe_fund",
                "ths_invest_philosophy_fund",
                "ths_invest_strategy_fund",
                "ths_risk_return_characteristics_fund",
                "ths_accum_dividend_total_amt_fund",
                "ths_accum_dividend_times_fund",
            ]
        )
    )


def _label_for_field(field: str) -> str:
    return field_meta(field)[0]


def _strip_raw_value(clause: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in clause.items() if key != "raw_value"}
