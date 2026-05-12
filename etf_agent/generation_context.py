from __future__ import annotations

import re
from typing import Any

from .candidates import PERIOD_FIELDS
from .capability_registry import COMPARE_FIELDS, LIST_BASELINE_FIELDS, field_meta, get_selection_context
from .report_scope import default_report_expand, report_collection, resolve_report_scope


IDENTITY_CONTEXT_FIELDS = {"fundcode", "ths_fund_extended_inner_short_name_fund"}
LEGACY_YIELD_FIELD_RE = re.compile(r"^ths_yeild_(1w|1m|3m|6m|1y|2y|3y|5y|ytd|std)_fund$")
PERIOD_LABELS = {
    "1w": "近1周收益率",
    "1m": "近1月收益率",
    "3m": "近3月收益率",
    "6m": "近半年收益率",
    "1y": "近1年收益率",
    "2y": "近2年收益率",
    "3y": "近3年收益率",
    "5y": "近5年收益率",
    "ytd": "今年以来收益率",
    "std": "成立以来收益率",
}

_EXPLICIT_DERIVED_PERFORMANCE_TRIGGERS = (
    "按净值序列重新计算",
    "自定义日期区间",
    "自定义日期",
    "指定日期区间",
    "按净值重新计算",
    "从某天到某天",
    "从某日到某日",
)


def build_generation_bundle(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
    phase: str = "v3.2",
) -> dict[str, Any]:
    selection_context = get_selection_context(query_mode, intent, phase=phase)
    report_scope = resolve_report_scope(question, intent, entity_hints) if query_mode == "report" else None
    if report_scope:
        selection_context["collection"] = report_collection(intent, report_scope, selection_context["collection"])
    evidence = _build_evidence(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints)
    expectations = _build_expectations(
        question,
        query_mode=query_mode,
        intent=intent,
        entity_hints=entity_hints,
        phase=phase,
    )
    if report_scope:
        expand = default_report_expand(question, intent, report_scope)
        expectations["report_scope"] = report_scope
        expectations["expected_expand"] = expand
        evidence["report_scope"] = report_scope
        evidence["report_period"] = entity_hints.get("report_period")
    if phase == "v3.3":
        _apply_v3_3_derived_contract(question, query_mode, intent, entity_hints, selection_context, evidence, expectations)
        expected_timeseries_modes = _expected_timeseries_modes(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints)
        if expected_timeseries_modes:
            expectations["expected_timeseries_modes"] = expected_timeseries_modes

    llm_context = {
        "ast_schema_version": selection_context.get("ast_schema_version", "v3_3_structured_query" if phase == "v3.3" else "v3_2_base_ast"),
        "phase": phase,
        "grammar_fragment_id": selection_context.get("grammar_fragment_id"),
        "compiler_rule_id": selection_context.get("compiler_rule_id"),
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
    }
    if "v3_3" in expectations:
        llm_context["derived_performance_contract"] = expectations["v3_3"]
    if expectations.get("expected_timeseries_modes"):
        llm_context["timeseries_contract"] = expectations["expected_timeseries_modes"]

    return {
        "llm_context": llm_context,
        "selection_context": selection_context,
        "validator_expectations": expectations,
    }


def _strict_validation_contract(expectations: dict[str, Any]) -> dict[str, Any]:
    required_answer_fields = (
        expectations["required_answer_fields"]
        if "required_answer_fields" in expectations
        else expectations.get("required_select_fields")
    )
    contract = {
        "required_select_fields": list(expectations.get("required_select_fields") or []),
        "required_answer_fields": list(required_answer_fields or []),
        "expected_where": [dict(item) for item in expectations.get("expected_where") or []],
        "expected_order_by": expectations.get("expected_order_by"),
        "expected_limit": expectations.get("expected_limit"),
        "expected_sub_intents": list(expectations.get("expected_sub_intents") or []),
        "expected_timeseries_modes": dict(expectations.get("expected_timeseries_modes") or {}),
        "report_scope": expectations.get("report_scope"),
        "expected_expand": expectations.get("expected_expand"),
    }
    contract.update(expectations.get("v3_3") or {})
    return contract


def _apply_v3_3_derived_contract(
    question: str,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
    evidence: dict[str, Any],
    expectations: dict[str, Any],
) -> None:
    if not _requires_explicit_derived_performance(question, entity_hints):
        return
    if intent not in {"performance", "filter", "compare", "composite_single"}:
        return
    period = entity_hints.get("period") or "1y"
    profile = _v3_3_profile(question, query_mode, intent)
    aliases = _derived_aliases_for_expectations(
        expectations,
        fallback_aliases=_v3_3_required_aliases(profile, period, question),
    )
    required_select_fields = _rewrite_legacy_yield_fields(expectations.get("required_select_fields") or [])
    for alias in aliases:
        if alias not in required_select_fields:
            required_select_fields.append(alias)
    expectations["required_select_fields"] = required_select_fields
    if profile == "derived_performance_table":
        expectations["required_answer_fields"] = list(selection_context.get("baseline_answer_fields") or ["fundcode"])
    else:
        expectations["required_answer_fields"] = list(required_select_fields)
    expectations["expected_where"] = [
        _rewrite_legacy_yield_clause(clause)
        for clause in expectations.get("expected_where") or []
    ]
    if isinstance(expectations.get("expected_order_by"), dict):
        expectations["expected_order_by"] = _rewrite_legacy_yield_order_by(expectations["expected_order_by"])
    primary_period = _period_from_alias(aliases[0]) if aliases else period
    expectations["v3_3"] = {
        "ast_schema_version": "v3_3_structured_query",
        "grammar_fragment_id": "derived_performance",
        "compiler_rule_id": profile,
        "allowed_profiles": [profile],
        "required_derived_aliases": aliases,
        "required_performance_rows": aliases if profile in {"derived_performance_table", "composite_single"} else [],
        "performance_row_labels": {alias: PERIOD_LABELS.get(_period_from_alias(alias) or "", alias) for alias in aliases},
        "period_defaults": {"default": primary_period},
        "range_aliases": list(aliases),
        "allowed_rank_sort_fields": [f"ths_yeild_rank_{primary_period}_fund", f"ths_yeild_rank_{primary_period}_etf"],
    }
    _register_derived_aliases(selection_context, aliases)
    evidence["allowed_profiles"] = [profile]
    evidence["period"] = primary_period
    evidence["required_derived_aliases"] = list(aliases)
    selection_context["ast_schema_version"] = "v3_3_structured_query"
    selection_context["grammar_fragment_id"] = "derived_performance"
    selection_context["compiler_rule_id"] = profile


def _filter_requires_derived_performance(question: str, entity_hints: dict[str, Any]) -> bool:
    return _requires_explicit_derived_performance(question, entity_hints)


def _requires_explicit_derived_performance(question: str, entity_hints: dict[str, Any]) -> bool:
    text = question.replace(" ", "")
    if any(trigger in text for trigger in _EXPLICIT_DERIVED_PERFORMANCE_TRIGGERS):
        return True
    if "从" in text and "到" in text and any(word in text for word in ("涨了多少", "收益率", "收益", "回报", "涨幅", "表现")):
        return True
    return bool(entity_hints.get("derived_performance"))


def _expectations_contain_legacy_yield(expectations: dict[str, Any]) -> bool:
    for field in expectations.get("required_select_fields") or []:
        if _legacy_yield_field_to_alias(field):
            return True
    for clause in expectations.get("expected_where") or []:
        if isinstance(clause, dict) and _legacy_yield_field_to_alias(clause.get("field")):
            return True
    order_by = expectations.get("expected_order_by")
    return isinstance(order_by, dict) and _legacy_yield_field_to_alias(order_by.get("field")) is not None


def _register_derived_aliases(selection_context: dict[str, Any], aliases: list[str]) -> None:
    for alias in aliases:
        if alias not in selection_context["selectable_fields"]:
            selection_context["selectable_fields"].append(alias)
        if alias not in selection_context["filterable_fields"]:
            selection_context["filterable_fields"].append(alias)
        if alias not in selection_context["sortable_fields"]:
            selection_context["sortable_fields"].append(alias)
        selection_context["field_operators"][alias] = ["eq", "gt", "gte", "lt", "lte"]
        selection_context["value_schemas"][alias] = "percent"
        selection_context["semantic_roles"][alias] = "semantic"
        selection_context["field_metas"][alias] = {
            "label": PERIOD_LABELS.get(_period_from_alias(alias) or "", alias),
            "format": "percent",
        }


def _v3_3_profile(question: str, query_mode: str, intent: str) -> str:
    if intent == "composite_single":
        return "composite_single"
    if query_mode == "compare":
        return "derived_return_list"
    if query_mode in {"filter", "search"} or any(word in question for word in ("前", "top", "哪些", "筛选", "超过", "最高", "最低", "排序")):
        return "derived_return_list"
    return "derived_performance_table"


def _v3_3_required_aliases(profile: str, period: str, question: str) -> list[str]:
    if period == "all":
        return [f"return_{item}" for item in ("1w", "1m", "3m", "6m", "1y", "2y", "3y", "5y", "ytd", "std")]
    return [f"return_{period}"]


def _derived_aliases_for_expectations(expectations: dict[str, Any], *, fallback_aliases: list[str]) -> list[str]:
    aliases: list[str] = []
    for field in expectations.get("required_select_fields") or []:
        alias = _legacy_yield_field_to_alias(field)
        if alias:
            aliases.append(alias)
    for clause in expectations.get("expected_where") or []:
        alias = _legacy_yield_field_to_alias(clause.get("field") if isinstance(clause, dict) else None)
        if alias:
            aliases.append(alias)
    order_by = expectations.get("expected_order_by")
    if isinstance(order_by, dict):
        alias = _legacy_yield_field_to_alias(order_by.get("field"))
        if alias:
            aliases.append(alias)
    return list(dict.fromkeys(aliases or fallback_aliases))


def _rewrite_legacy_yield_fields(fields: list[str]) -> list[str]:
    rewritten = []
    for field in fields:
        rewritten.append(_legacy_yield_field_to_alias(field) or field)
    return list(dict.fromkeys(rewritten))


def _rewrite_legacy_yield_clause(clause: dict[str, Any]) -> dict[str, Any]:
    rewritten = dict(clause)
    alias = _legacy_yield_field_to_alias(rewritten.get("field"))
    if alias:
        rewritten["field"] = alias
    return rewritten


def _rewrite_legacy_yield_order_by(order_by: dict[str, Any]) -> dict[str, Any]:
    rewritten = dict(order_by)
    alias = _legacy_yield_field_to_alias(rewritten.get("field"))
    if alias:
        rewritten["field"] = alias
    return rewritten


def _legacy_yield_field_to_alias(field: Any) -> str | None:
    if not isinstance(field, str):
        return None
    match = LEGACY_YIELD_FIELD_RE.match(field)
    if not match:
        return None
    return f"return_{match.group(1)}"


def _period_from_alias(alias: str) -> str | None:
    if not alias.startswith("return_"):
        return None
    return alias.removeprefix("return_")


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
    if query_mode == "report":
        return {"default": 1, "max": 20}
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
    phase: str,
) -> dict[str, Any]:
    return {
        "required_select_fields": _required_select_fields(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "display_default_fields": _display_default_fields(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "expected_where": _expected_where(query_mode, entity_hints),
        "expected_order_by": _expected_order_by(question, query_mode, entity_hints),
        "expected_limit": entity_hints.get("limit_hint"),
        "expected_sub_intents": _expected_sub_intents(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
        "expected_timeseries_modes": _expected_timeseries_modes(question, query_mode=query_mode, intent=intent, entity_hints=entity_hints),
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
    if query_mode == "report":
        expand = default_report_expand(question, intent, resolve_report_scope(question, intent, entity_hints))
        if expand:
            return [expand["field"], *expand.get("paired_fields", [])]
        if intent == "institution_holding":
            return ["ths_org_investor_total_held_ratio_fund", "ths_org_investor_total_held_shares_fund"]
        if intent == "report_style":
            return ["ths_invest_style_fund"]
        if intent == "report_nav_change":
            return ["ths_fanv_chg_fund", "ths_fanv_chg_rate_fund"]
        return []
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
    if query_mode == "report":
        expand = default_report_expand(question, intent, resolve_report_scope(question, intent, entity_hints))
        if expand:
            return [expand["field"], *expand.get("paired_fields", [])]
        if intent == "institution_holding":
            return ["ths_org_investor_total_held_ratio_fund", "ths_org_investor_total_held_shares_fund"]
        if intent == "report_style":
            return ["ths_invest_style_fund"]
        if intent == "report_nav_change":
            return ["ths_fanv_chg_fund", "ths_fanv_chg_rate_fund"]
        return []
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
    if query_mode in {"single", "report"} and fundcodes:
        return [{"field": "fundcode", "op": "eq", "value": fundcodes[0]}]
    if query_mode == "search":
        return [{"field": "__search_text__", "op": "contains", "value": str(entity_hints.get("search_keyword") or "")}]
    if query_mode == "filter":
        return [dict(item) for item in entity_hints.get("filters") or []]
    if query_mode == "compare" and len(fundcodes) >= 2:
        return [{"field": "fundcode", "op": "in", "value": fundcodes[:10]}]
    return []


def _expected_order_by(
    question: str,
    query_mode: str,
    entity_hints: dict[str, Any],
) -> dict[str, str] | None:
    explicit = entity_hints.get("order_by")
    if isinstance(explicit, dict):
        return dict(explicit)
    return None


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
    for sub_intent, cues in _composite_single_evidence_rules():
        position = _first_evidence_position(question, cues)
        if position is not None:
            sub_intents.append((position, sub_intent))
    sub_intents.sort(key=lambda item: item[0])
    return list(dict.fromkeys(sub_intent for _position, sub_intent in sub_intents))


def _composite_single_required_fields(question: str) -> list[str]:
    fields = ["fundcode", "ths_fund_extended_inner_short_name_fund"]
    for sub_intent in _expected_sub_intents(question, query_mode="single", intent="composite_single", entity_hints={}):
        if sub_intent == "basic_info":
            fields.extend(["ths_name_of_tracking_index_fund", "ths_fund_scale_fund"])
        elif sub_intent == "performance":
            fields.extend(_performance_required_fields(question, "std"))
        elif sub_intent == "fund_scale":
            fields.extend(_composite_single_scale_fields(question))
        elif sub_intent == "fee":
            fields.extend(_composite_single_fee_fields(question))
        elif sub_intent == "manager":
            fields.extend(["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"])
        elif sub_intent == "basic_info_extended":
            fields.extend(_composite_single_basic_info_extended_fields(question))
        elif sub_intent == "report_industry":
            fields.extend(["ths_top_n_top_industry_name_fund", "ths_top_n_top_industry_mv_to_equity_fund"])
        elif sub_intent == "report_holding":
            fields.extend(["ths_top_held_stock_code_fund", "ths_top_stock_mv_to_fnv_fund", "ths_top_sec_code_fund", "ths_top_n_top_stock_mv_to_equity_fund"])
        elif sub_intent == "report_concept":
            fields.append("ths_zcgnmc_fund")
        elif sub_intent == "institution_holding":
            fields.extend(["ths_org_investor_total_held_ratio_fund", "ths_org_investor_total_held_shares_fund"])
        elif sub_intent == "report_style":
            fields.append("ths_invest_style_fund")
        elif sub_intent == "report_nav_change":
            fields.extend(["ths_fanv_chg_fund", "ths_fanv_chg_rate_fund"])
        elif sub_intent == "dividend":
            fields.extend(["ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"])
    return list(dict.fromkeys(fields))


def _expected_timeseries_modes(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
) -> dict[str, dict[str, str]]:
    modes: dict[str, dict[str, str]] = {}
    if "最近有变化" in question or "变化吗" in question or "变化" in question:
        if "份额" in question:
            modes["ths_fund_shares_fund"] = {"mode": "latest_two", "evidence": "最近有变化"}
    if any(word in question for word in ("最近成交额", "成交额", "净现金流", "融资余额", "融券卖出量")):
        field_map = {
            "ths_amt_fund": "成交额",
            "ths_netcashflow_fund": "净现金流",
            "ths_margin_trading_balance_fund": "融资余额",
            "ths_short_selling_amtb_fund": "融券卖出量",
        }
        for field, evidence in field_map.items():
            if evidence in question:
                modes[field] = {"mode": "latest", "evidence": evidence}
    return modes


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


def _composite_single_evidence_rules() -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("basic_info", ("基本信息", "是什么", "介绍", "概况")),
        ("performance", ("收益", "排名", "涨", "跌")),
        ("fund_scale", ("规模", "盘子", "市值", "份额", "净值")),
        ("fee", ("管理费", "托管费", "费率")),
        ("manager", ("管理人", "基金经理")),
        ("basic_info_extended", ("申赎", "申购", "赎回", "联接")),
        ("report_industry", ("持仓行业", "行业配置", "行业持仓", "行业", "持仓")),
        ("report_holding", ("重仓股", "前十大", "重仓证券")),
        ("report_concept", ("重仓概念", "概念")),
        ("institution_holding", ("机构持有",)),
        ("report_style", ("投资风格", "风格")),
        ("report_nav_change", ("净资产变动", "净资产变化")),
        ("dividend", ("分红", "分过红")),
    ]


def _first_evidence_position(question: str, cues: tuple[str, ...]) -> int | None:
    positions = [question.find(cue) for cue in cues if cue in question]
    if not positions:
        return None
    return min(positions)


def _composite_single_scale_fields(question: str) -> list[str]:
    fields: list[str] = []
    if any(word in question for word in ("规模", "盘子", "资产规模", "基金规模", "多大")):
        fields.append("ths_fund_scale_fund")
    if "总市值" in question or "市值" in question:
        fields.append("ths_current_mv_fund")
    if "份额" in question:
        fields.append("ths_fund_shares_fund")
    if "净值增长率" in question:
        fields.append("ths_unit_nvg_rate_fund")
    elif "净值" in question or "最新净值" in question:
        fields.append("ths_unit_nv_fund")
    return list(dict.fromkeys(fields))


def _composite_single_fee_fields(question: str) -> list[str]:
    fields: list[str] = []
    if any(word in question for word in ("管理费", "费率", "费用")):
        fields.append("ths_manage_fee_rate_fund")
    if "托管费" in question:
        fields.append("ths_mandate_fee_rate_fund")
    return list(dict.fromkeys(fields))


def _composite_single_basic_info_extended_fields(question: str) -> list[str]:
    fields: list[str] = []
    if ("成立" in question and "成立以来" not in question):
        fields.append("ths_fund_establishment_date_fund")
    if "上市" in question:
        fields.append("ths_fund_listed_exchange_fund")
    if "业绩比较基准" in question or "比较基准" in question:
        fields.append("ths_perf_comparative_benchmark_fund")
    if "申赎" in question or "申购" in question or "赎回" in question:
        fields.append("ths_pur_and_redemp_status_fund")
    if "联接" in question:
        fields.append("ths_etf_to_code_fund")
    return list(dict.fromkeys(fields))


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
                "ths_fund_scale_fund",
                "ths_fund_shares_fund",
                "ths_unit_nv_fund",
                "ths_unit_nvg_rate_fund",
                "ths_current_mv_fund",
                "ths_manage_fee_rate_fund",
                "ths_mandate_fee_rate_fund",
                "ths_top_n_top_industry_name_fund",
                "ths_top_n_top_industry_mv_to_equity_fund",
                "ths_zcgnmc_fund",
                "ths_top_held_stock_code_fund",
                "ths_top_stock_mv_to_fnv_fund",
                "ths_top_sec_code_fund",
                "ths_top_n_top_stock_mv_to_equity_fund",
                "ths_org_investor_total_held_ratio_fund",
                "ths_org_investor_total_held_shares_fund",
                "ths_invest_style_fund",
                "ths_fanv_chg_fund",
                "ths_fanv_chg_rate_fund",
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
