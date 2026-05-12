from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


RETURN_OFFSETS = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 250,
    "2y": 500,
    "3y": 750,
    "5y": 1250,
}

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


def compile_derived_performance_query(ast: dict[str, Any]) -> dict[str, Any]:
    metrics = _derived_metrics(ast)
    profile = ast.get("profile") or _default_derived_profile(ast)
    performance_rows = _output_performance_rows(ast, metrics)
    physical_projection = ["fundcode"]
    if metrics:
        physical_projection.append("ths_unit_nv_fund")
    for field in ast.get("select") or []:
        if isinstance(field, str) and field.startswith("ths_") and field not in physical_projection:
            physical_projection.append(field)

    mongo_phase = {
        "collection": ast["from"],
        "filter": _mongo_filter(ast.get("where") or []),
        "projection": physical_projection,
        "limit": ast["limit"],
        "answer_fields": [
            item for item in ast.get("answer_fields", []) if item.get("field") not in {metric["alias"] for metric in metrics}
        ],
        "output_style": ast.get("output_style", "summary"),
    }
    if ast.get("order_by") and ast["order_by"]["field"] not in {metric["alias"] for metric in metrics}:
        mongo_phase["sort"] = _sort_spec(ast["order_by"])

    order_by = ast.get("order_by")
    derived_aliases = {metric["alias"] for metric in metrics}
    return {
        "ast_schema_version": ast.get("ast_schema_version", "v3_3_structured_query"),
        "grammar_fragment_id": ast.get("grammar_fragment_id", "derived_performance"),
        "compiler_rule_id": ast.get("compiler_rule_id", profile),
        "mongo_phase": mongo_phase,
        "derived_phase": {
            "profile": profile,
            "metrics": metrics,
            "filters": [clause for clause in ast.get("where") or [] if clause.get("field") in derived_aliases],
            "order_by": order_by if isinstance(order_by, dict) and order_by.get("field") in derived_aliases else None,
            "limit": ast["limit"],
        },
        "output_phase": {
            "output_style": ast.get("output_style", "summary"),
            "filter": mongo_phase["filter"],
            "answer_fields": list(ast.get("answer_fields") or []),
            "performance_rows": performance_rows,
        },
        "provenance": {
            "source": "llm_draft_ast",
            "ast_schema_version": ast.get("ast_schema_version", "v3_3_structured_query"),
            "grammar_fragment_id": ast.get("grammar_fragment_id", "derived_performance"),
            "compiler_rule_id": ast.get("compiler_rule_id", profile),
            "nav_field": "ths_unit_nv_fund",
            "formula": "(end_nav - start_nav) / start_nav * 100",
        },
    }


def execute_derived_performance(compiled_query: dict[str, Any], mongo_result: dict[str, Any]) -> dict[str, Any]:
    data = mongo_result.get("data")
    if isinstance(data, list):
        rows = [dict(row) for row in data if isinstance(row, dict)]
        list_mode = True
    elif isinstance(data, dict):
        rows = [dict(data)]
        list_mode = False
    else:
        rows = []
        list_mode = False

    audit = {
        "candidate_count_total": len(rows),
        "candidate_count_loaded": len(rows),
        "derived_value_valid_count": 0,
        "derived_value_missing_count": 0,
        "invalid_nav_count": 0,
    }
    metrics = compiled_query["derived_phase"].get("metrics") or []
    output_rows = []
    for row in rows:
        enriched = dict(row)
        row_valid = True
        for metric in metrics:
            value = calculate_return(row.get("ths_unit_nv_fund"), metric["period"])
            if value is None:
                audit["derived_value_missing_count"] += 1
                audit["invalid_nav_count"] += 1
                row_valid = False
            else:
                audit["derived_value_valid_count"] += 1
            enriched[metric["alias"]] = value
        if list_mode and metrics and not row_valid:
            continue
        output_rows.append(enriched)

    output_rows = _apply_derived_filters(output_rows, compiled_query["derived_phase"].get("filters") or [])
    output_rows = _apply_derived_sort(output_rows, compiled_query["derived_phase"].get("order_by"))
    if list_mode:
        output_rows = output_rows[: int(compiled_query["derived_phase"].get("limit") or len(output_rows))]
        result_data: Any = output_rows
    else:
        result_data = output_rows[0] if output_rows else None

    return {"success": True, "data": result_data, "derived_audit": audit}


def calculate_return(raw_nav: Any, period: str) -> float | None:
    points = _nav_points(raw_nav)
    if len(points) < 2:
        return None
    end = points[-1]
    if period == "std":
        start = points[0]
    elif period == "ytd":
        start = _first_point_in_year(points, end[0].year)
    else:
        offset = RETURN_OFFSETS.get(period)
        if offset is None or len(points) <= offset:
            start = points[0]
        else:
            start = points[-1 - offset]
    if start is None or start[1] in {None, 0} or end[1] is None:
        return None
    return round((end[1] - start[1]) / start[1] * 100, 10)


def _nav_points(raw_nav: Any) -> list[tuple[date, float]]:
    if isinstance(raw_nav, str):
        try:
            raw_nav = json.loads(raw_nav)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_nav, list):
        return []
    by_date: dict[date, float] = {}
    for item in raw_nav:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("btime") or item.get("date")
        raw_value = item.get("value")
        parsed_date = _parse_date(raw_date)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if parsed_date is None or value <= 0:
            continue
        by_date[parsed_date] = value
    return sorted(by_date.items(), key=lambda item: item[0])


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def _first_point_in_year(points: list[tuple[date, float]], year: int) -> tuple[date, float] | None:
    for point in points:
        if point[0].year == year:
            return point
    return None


def _derived_metrics(ast: dict[str, Any]) -> list[dict[str, str]]:
    rows = {row.get("alias"): row for row in ast.get("performance_rows") or [] if isinstance(row, dict)}
    metrics = []
    for field in ast.get("select") or []:
        if not isinstance(field, str) or not field.startswith("return_"):
            continue
        period = str((rows.get(field) or {}).get("period") or field.removeprefix("return_"))
        metrics.append({"alias": field, "period": period, "label": str((rows.get(field) or {}).get("label") or _period_label(period, field))})
    return metrics


def _output_performance_rows(ast: dict[str, Any], metrics: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [dict(row) for row in ast.get("performance_rows") or [] if isinstance(row, dict)]
    if rows or ast.get("output_style") != "performance_table":
        return rows
    return [
        {"alias": metric["alias"], "period": metric["period"], "label": metric["label"]}
        for metric in metrics
    ]


def _default_derived_profile(ast: dict[str, Any]) -> str:
    output_style = ast.get("output_style")
    if output_style == "performance_table":
        return "derived_performance_table"
    if output_style == "summary":
        return "composite_single"
    if output_style == "compare":
        return "derived_return_list"
    return "derived_return_list"


def _period_label(period: str, fallback: str) -> str:
    return PERIOD_LABELS.get(period, fallback)


def _mongo_filter(where: list[dict[str, Any]]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for clause in where:
        field = clause.get("field")
        if not isinstance(field, str) or field.startswith("return_"):
            continue
        op = clause.get("op")
        if op == "eq":
            query[field] = clause.get("value")
        elif op == "in":
            query[field] = {"$in": clause.get("value")}
        elif op in {"gt", "gte", "lt", "lte"}:
            query.setdefault(field, {})[{"gt": "$gt", "gte": "$gte", "lt": "$lt", "lte": "$lte"}[op]] = clause.get("value")
    return query


def _sort_spec(order_by: dict[str, str]) -> list[list[Any]]:
    direction = -1 if order_by.get("direction") == "desc" else 1
    return [[order_by["field"], direction], ["fundcode", 1]]


def _apply_derived_filters(rows: list[dict[str, Any]], filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for clause in filters:
        rows = [row for row in rows if _matches(row.get(clause["field"]), clause.get("op"), clause.get("value"))]
    return rows


def _matches(value: Any, op: str, threshold: Any) -> bool:
    if value is None:
        return False
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    if op == "eq":
        return value == threshold
    return False


def _apply_derived_sort(rows: list[dict[str, Any]], order_by: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not order_by:
        return rows
    reverse = order_by.get("direction") == "desc"
    field = order_by["field"]
    return sorted(rows, key=lambda row: (row.get(field) is None, row.get(field)), reverse=reverse)
