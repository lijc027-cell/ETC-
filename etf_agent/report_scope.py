from __future__ import annotations

from typing import Any


REPORT_SCOPE_VALUES = {"year_latest", "quarter_latest", "year_list", "quarter_list"}
YEAR_REPORT_TYPES = [4, 6]
QUARTER_REPORT_TYPES = [1, 2, 3]

REPORT_ARRAY_FIELDS = {
    "report_holding": {
        "field": "ths_top_held_stock_code_fund",
        "paired_fields": ["ths_top_stock_mv_to_fnv_fund"],
    },
    "report_industry": {
        "field": "ths_top_n_top_industry_name_fund",
        "paired_fields": ["ths_top_n_top_industry_mv_to_equity_fund"],
    },
    "report_concept": {
        "field": "ths_zcgnmc_fund",
        "paired_fields": [],
    },
}

REPORT_SCALAR_INTENTS = {"institution_holding", "report_style", "report_nav_change"}


_QUARTER_KEYWORDS = ("季报", "Q1", "Q2", "Q3", "q1", "q2", "q3", "一季报", "中报", "半年报", "三季报", "一季度", "三季度")


def resolve_report_scope(question: str, intent: str, entity_hints: dict[str, Any] | None = None) -> str | None:
    hints = entity_hints or {}
    explicit = hints.get("report_scope")
    if explicit in REPORT_SCOPE_VALUES:
        return str(explicit)
    if intent not in REPORT_ARRAY_FIELDS and intent not in REPORT_SCALAR_INTENTS:
        return None

    list_suffix = "_list" if _wants_report_list(question) else "_latest"
    if intent in REPORT_SCALAR_INTENTS:
        return f"year{list_suffix}"
    if intent == "report_holding":
        if any(word in question for word in _QUARTER_KEYWORDS):
            return f"quarter{list_suffix}"
        return f"year{list_suffix}"
    if intent == "report_concept":
        return f"quarter{list_suffix}"
    if intent == "report_industry":
        if "年报" in question:
            return f"year{list_suffix}"
        return f"quarter{list_suffix}"
    return None


def report_collection(intent: str, report_scope: str | None, fallback: str) -> str:
    if intent in REPORT_SCALAR_INTENTS:
        return "tb_ths_etf_report_year"
    if intent == "report_holding":
        if report_scope and report_scope.startswith("quarter"):
            return "tb_ths_etf_report_quarter"
        return "tb_ths_etf_report_year"
    if intent == "report_concept":
        return "tb_ths_etf_report_quarter"
    if intent == "report_industry" and report_scope and report_scope.startswith("quarter"):
        return "tb_ths_etf_report_quarter"
    if intent == "report_industry" and report_scope and report_scope.startswith("year"):
        return "tb_ths_etf_report_year"
    return fallback


def report_type_filter(report_scope: str | None) -> list[int] | None:
    if not report_scope:
        return None
    if report_scope.startswith("year"):
        return list(YEAR_REPORT_TYPES)
    if report_scope.startswith("quarter"):
        return list(QUARTER_REPORT_TYPES)
    return None


def default_report_expand(question: str, intent: str, report_scope: str | None) -> dict[str, Any] | None:
    spec = REPORT_ARRAY_FIELDS.get(intent)
    if spec is None:
        return None
    paired_fields = list(spec["paired_fields"])
    if intent == "report_industry" and report_scope and report_scope.startswith("quarter"):
        paired_fields = []
    order_by = {"field": "rank_num", "direction": "asc"}
    if intent == "report_industry" and paired_fields and any(word in question for word in ("占比最高", "按占比", "占比从高到低", "占比降序")):
        order_by = {"field": paired_fields[0], "direction": "desc"}
    return {
        "field": spec["field"],
        "paired_fields": paired_fields,
        "order_by": order_by,
    }


def _wants_report_list(question: str) -> bool:
    return any(word in question for word in ("历年", "各年", "每年", "历季", "各季", "每季"))
