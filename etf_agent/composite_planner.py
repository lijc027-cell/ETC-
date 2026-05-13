from __future__ import annotations

import re
from typing import Any


def build_composite_plan(question: str, *, entity_hints: dict[str, Any] | None = None) -> dict[str, Any]:
    hints = entity_hints or {}
    sub_intents = _sub_intents(_answer_question_part(question))
    return {
        "plan_type": _plan_type(question),
        "selection": _selection(question, hints),
        "target_cardinality": _target_cardinality(question),
        "answer_bundle": {"sub_intents": sub_intents},
        "report_policy": _report_policy(sub_intents),
        "output_policy": _output_policy(question),
    }


def _plan_type(question: str) -> str:
    if any(phrase in question for phrase in ("然后看它", "查一下它", "对比它们", "比较它们", "对比一下")):
        return "two_step_composite"
    return "composite_single"


def _selection(question: str, hints: dict[str, Any]) -> dict[str, Any]:
    mode = "none"
    if _has_search_signal(question) and not _has_filter_signal(question):
        mode = "search"
    elif _has_filter_signal(question):
        mode = "filter"

    constraints = list(hints.get("filters") or [])
    if not constraints:
        constraints = _filter_constraints(question)

    order_by = list(hints.get("order_by") and [hints["order_by"]] or [])
    if not order_by:
        order_by = _order_by(question)

    return {
        "mode": mode,
        "constraints": constraints,
        "order_by": order_by,
        "limit": _limit(question),
        "tie_breakers": _tie_breakers(question),
        "search_keyword": str(hints.get("search_keyword") or _search_keyword(question)),
    }


def _target_cardinality(question: str) -> str:
    if any(word in question for word in ("对比它们", "比较它们", "对比一下")):
        return "list"
    if _limit(question) and _limit(question) > 1 and any(word in question for word in ("对比", "比较")):
        return "list"
    return "single"


def _output_policy(question: str) -> str:
    if any(word in question for word in ("对比", "比较")):
        return "compare"
    if "基本信息" in question or "持仓" in question:
        return "detail"
    return "summary"


def _report_policy(sub_intents: list[str]) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    if "report_holding" in sub_intents:
        policy["report_holding"] = {
            "resolved_report_scope": "year_latest",
            "scope_reason": "holding_fields_available_only_in_year_report",
            "user_note": "重仓股当前按最新年报口径展示",
        }
    if "report_industry" in sub_intents:
        policy["report_industry"] = {"resolved_report_scope": "quarter_latest"}
    if "report_concept" in sub_intents:
        policy["report_concept"] = {"resolved_report_scope": "quarter_latest"}
    return policy


def _sub_intents(question: str) -> list[str]:
    sub_intents: list[str] = []
    if any(word in question for word in ("基本信息", "是什么", "介绍", "概况")):
        sub_intents.append("basic_info")
    if any(word in question for word in ("收益", "排名", "涨", "跌")):
        sub_intents.append("performance")
    if any(word in question for word in ("规模", "盘子", "市值", "份额", "净值")):
        sub_intents.append("fund_scale")
    if any(word in question for word in ("管理费", "托管费", "费率")):
        sub_intents.append("fee")
    if any(word in question for word in ("管理了多久", "历史业绩", "管理规模", "管了多少规模", "什么时候换的基金经理", "换的基金经理", "任职", "任期", "历任")):
        sub_intents.append("manager_detail")
    elif any(word in question for word in ("基金经理是谁", "谁在管", "谁在管理", "基金经理", "管理人")):
        sub_intents.append("manager")
    if any(word in question for word in ("申赎", "申购", "赎回", "联接", "上市", "业绩比较基准", "成立于", "成立日期")):
        sub_intents.append("basic_info_extended")
    if "持仓" in question and not any(word in question for word in ("重仓股", "前十大", "重仓证券", "行业", "概念")):
        sub_intents.extend(["report_industry", "report_concept"])
    if any(word in question for word in ("持仓行业", "行业配置", "行业持仓", "行业")):
        sub_intents.append("report_industry")
    if any(word in question for word in ("重仓股", "前十大", "重仓证券")):
        sub_intents.append("report_holding")
    if any(word in question for word in ("重仓概念", "概念")):
        sub_intents.append("report_concept")
    if "分红" in question or "分过红" in question:
        sub_intents.append("dividend")
    return list(dict.fromkeys(sub_intents))


def _answer_question_part(question: str) -> str:
    for marker in ("然后看它", "查一下它", "看它", "然后查它"):
        if marker in question:
            tail = question.split(marker, 1)[1]
            return tail or question
    if any(marker in question for marker in ("对比它们", "对比一下", "比较它们", "比较一下")):
        return question
    return question


def _filter_constraints(question: str) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    if "上交所" in question or "沪市" in question:
        constraints.append({"field": "ths_fund_listed_exchange_fund", "op": "eq", "value": "上交所"})
    if "股票型" in question:
        constraints.append({"field": "ths_fund_invest_type_fund", "op": "eq", "value": "股票型"})
    if "沪深300" in question and "跟踪" in question:
        constraints.append({"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "沪深300指数", "raw_value": "沪深300"})
    if _is_lowest_fee(question):
        constraints.append({"field": "ths_manage_fee_rate_fund", "op": "eq", "value": 0.15})
    return constraints


def _order_by(question: str) -> list[dict[str, str]]:
    if _is_lowest_fee(question):
        return [{"field": "ths_manage_fee_rate_fund", "direction": "asc"}]
    if "收益" in question and any(word in question for word in ("最高", "前", "最好", "排名")):
        return [{"field": "ths_yeild_ytd_fund", "direction": "desc"}]
    return []


def _tie_breakers(question: str) -> list[dict[str, str]]:
    if _is_lowest_fee(question):
        return [
            {"field": "ths_fund_scale_fund", "direction": "desc"},
            {"field": "fundcode", "direction": "asc"},
        ]
    return [{"field": "ths_fund_scale_fund", "direction": "desc"}, {"field": "fundcode", "direction": "asc"}]


def _limit(question: str) -> int | None:
    match = re.search(r"(?:前|top)\s*([0-9]+)", question, re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"([0-9]+)\s*只", question)
    if match:
        return int(match.group(1))
    return None


def _search_keyword(question: str) -> str:
    match = re.search(r"搜索([^，,。?？]+)", question)
    if match:
        return match.group(1).strip()
    return ""


def _is_lowest_fee(question: str) -> bool:
    return any(word in question for word in ("管理费", "费率")) and "最低" in question


def _has_search_signal(question: str) -> bool:
    return any(word in question for word in ("搜索", "帮我找", "找一下", "我想找"))


def _has_filter_signal(question: str) -> bool:
    return any(word in question for word in ("筛选", "上交所", "股票型", "最低", "最高", "前", "跟踪"))
