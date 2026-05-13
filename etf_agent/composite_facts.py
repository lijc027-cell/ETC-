from __future__ import annotations

from typing import Any


def build_child_facts(child_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for child in child_results:
        v3 = child.get("v3") or {}
        plan = child.get("query_plan") or {}
        result = child.get("result") or {}
        data = result.get("data")
        facts.append({
            "intent": v3.get("intent"),
            "mode": v3.get("recognized_query_mode"),
            "answer": str(child.get("answer") or "").strip(),
            "result": result,
            "query_plan": plan,
            "funds": _fund_facts(data, plan),
            "metadata": _metadata(data, plan),
        })
    return facts


def _fund_facts(data: Any, plan: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        rows = [data]
    elif isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
    else:
        rows = []
    intent = _intent_from_plan(plan)
    return [_row_facts(row, intent, plan) for row in rows]


def _row_facts(row: dict[str, Any], intent: str, plan: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if row.get("ths_fund_extended_inner_short_name_fund") is not None:
        facts["fund.name"] = _plain(row.get("ths_fund_extended_inner_short_name_fund"))
    for field, key, fmt in (
        ("ths_manage_fee_rate_fund", "fee.manage", "percent"),
        ("ths_mandate_fee_rate_fund", "fee.custody", "percent"),
        ("ths_fund_scale_fund", "scale.latest", "amount"),
        ("ths_yeild_ytd_fund", "performance.ytd", "percent"),
        ("ths_yeild_1y_fund", "performance.1y", "percent"),
        ("ths_yeild_std_fund", "performance.std", "percent"),
        ("ths_fund_manager_current_fund", "manager.current", "plain"),
        ("ths_fund_supervisor_fund", "manager.supervisor", "plain"),
    ):
        if row.get(field) is not None:
            facts[key] = _format_value(row.get(field), fmt)
    if intent == "report_industry":
        facts["report_industry.top"] = _top_array(row.get("ths_top_n_top_industry_name_fund"), 6)
    if intent == "report_concept":
        facts["report_concept.top"] = _top_array(row.get("ths_zcgnmc_fund"), 5)
    if intent == "report_holding":
        facts["report_holding.top_codes"] = _top_array(row.get("ths_top_held_stock_code_fund"), 10)
    return {
        "fundcode": str(row.get("fundcode") or ""),
        "fund_name": facts.get("fund.name"),
        "facts": facts,
        "metadata": _metadata(row, plan),
    }


def _metadata(data: Any, plan: dict[str, Any]) -> dict[str, Any]:
    row = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else data if isinstance(data, dict) else {}
    metadata: dict[str, Any] = {}
    data_as_of = _latest_btime(data)
    if data_as_of:
        metadata["data_as_of"] = data_as_of
    if isinstance(row, dict) and row.get("year_num"):
        metadata["report_period"] = _report_period(row)
    if plan.get("report_scope"):
        metadata["report_scope"] = plan.get("report_scope")
    return metadata


def _intent_from_plan(plan: dict[str, Any]) -> str:
    style = plan.get("output_style")
    if style == "report_list":
        fields = set(plan.get("projection") or [])
        if "ths_top_n_top_industry_name_fund" in fields:
            return "report_industry"
        if "ths_zcgnmc_fund" in fields:
            return "report_concept"
        if "ths_top_held_stock_code_fund" in fields:
            return "report_holding"
    return str(plan.get("intent") or "")


def _top_array(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    rows = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            raw = item.get("value")
            rank = item.get("rank_num") or index
        else:
            raw = item
            rank = index
        if raw in (None, "", "暂无数据"):
            continue
        rows.append((rank, str(raw)))
    rows.sort(key=lambda item: item[0])
    return [item[1] for item in rows[:limit]]


def _latest_btime(value: Any) -> str:
    dates: set[str] = set()
    _collect_btime(value, dates)
    return sorted(dates)[-1] if dates else ""


def _collect_btime(value: Any, dates: set[str]) -> None:
    if isinstance(value, dict):
        if value.get("btime"):
            dates.add(str(value["btime"]))
        for item in value.values():
            _collect_btime(item, dates)
    elif isinstance(value, list):
        for item in value:
            _collect_btime(item, dates)


def _report_period(row: dict[str, Any]) -> str:
    year = row.get("year_num")
    type_label = {1: "一季报", 2: "中报", 3: "三季报", 4: "年报", 6: "年报"}.get(_safe_int(row.get("type_num")), "")
    return f"{year}年{type_label}" if type_label else f"{year}年"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_value(value: Any, fmt: str) -> str:
    value = _latest_value(value)
    if value in (None, ""):
        return "暂无数据"
    if fmt == "percent":
        return f"{float(value):.2f}%"
    if fmt == "amount":
        return f"{float(value) / 100000000:.2f} 亿元"
    return str(value)


def _latest_value(value: Any) -> Any:
    if isinstance(value, list):
        points = [item for item in value if isinstance(item, dict) and item.get("value") is not None]
        if not points:
            return None
        return max(points, key=lambda item: str(item.get("btime", ""))).get("value")
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _plain(value: Any) -> str:
    latest = _latest_value(value)
    return "" if latest is None else str(latest)
