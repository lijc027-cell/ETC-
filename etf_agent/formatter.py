from __future__ import annotations

from typing import Any


def format_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    if plan.get("output_style") == "list":
        return _format_list_answer(plan, result)
    if plan.get("output_style") == "compare":
        return _format_compare_answer(plan, result)

    fundcode = plan.get("filter", {}).get("fundcode", "该 ETF")
    data = result.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        return f"未在 ETF 数据库中找到代码 {fundcode} 对应的 ETF。"

    parts = []
    for field in plan["answer_fields"]:
        name = field["field"]
        if name == "fundcode":
            continue
        parts.append(f"{field['label']}为 {_format_value(data.get(name), field.get('format', 'plain'))}")

    if not parts:
        return f"{fundcode} 暂无可展示字段。"
    return f"{fundcode} 的{'，'.join(parts)}。"


def chinese_mapping(plan: dict[str, Any]) -> dict[str, str]:
    return {item["field"]: item["label"] for item in plan["answer_fields"]}


def _format_value(value: Any, fmt: str) -> str:
    value, as_of = _latest_value(value)
    if value is None or value == "":
        return "暂无数据"
    suffix = f"（{as_of}）" if as_of else ""
    if fmt in {"yuan_to_100m", "amount"}:
        return f"{float(value) / 100000000:.2f} 亿元{suffix}"
    if fmt == "percent":
        return f"{float(value):.2f}%{suffix}"
    if isinstance(value, float):
        return f"{value:.4g}{suffix}"
    return f"{value}{suffix}"


def _format_list_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    rows = result.get("data") or []
    if not isinstance(rows, list) or not rows:
        return "未找到符合条件的 ETF。"

    fields = _list_fields(plan)
    labels = chinese_mapping({"answer_fields": plan["answer_fields"]})
    lines = [
        "| " + " | ".join(labels.get(field, field) for field in fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format_value(row.get(field), _field_format(plan, field)) for field in fields) + " |")
    return "\n".join(lines)


def _format_compare_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    rows = result.get("data") or []
    if not isinstance(rows, list) or not rows:
        return "未找到可对比的 ETF。"
    rows = _order_compare_rows(plan, rows)

    fundcodes = [str(row.get("fundcode", "未知")) for row in rows]
    labels = chinese_mapping({"answer_fields": plan["answer_fields"]})
    fields = [field["field"] for field in plan["answer_fields"] if field["field"] != "fundcode"]
    lines = [
        "| 指标 | " + " | ".join(fundcodes) + " |",
        "| --- | " + " | ".join("---" for _ in fundcodes) + " |",
    ]
    for field in fields:
        values = [_format_value(row.get(field), _field_format(plan, field)) for row in rows]
        lines.append("| " + labels.get(field, field) + " | " + " | ".join(values) + " |")
    missing = _missing_compare_codes(plan, rows)
    if missing:
        lines.append("")
        lines.append(f"缺失代码：{', '.join(missing)}")
    return "\n".join(lines)


def _list_fields(plan: dict[str, Any]) -> list[str]:
    fields = [field["field"] for field in plan["answer_fields"]]
    order_by = (plan.get("sort") or [[None]])[0][0]
    if order_by and order_by not in fields:
        fields.append(order_by)
    return fields


def _field_format(plan: dict[str, Any], field: str) -> str:
    for item in plan["answer_fields"]:
        if item["field"] == field:
            return item.get("format", "plain")
    return "plain"


def _missing_compare_codes(plan: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    fundcode_filter = plan.get("filter", {}).get("fundcode")
    if not isinstance(fundcode_filter, dict) or "$in" not in fundcode_filter:
        return []
    requested = [str(item) for item in fundcode_filter["$in"]]
    found = {str(row.get("fundcode")) for row in rows}
    return [fundcode for fundcode in requested if fundcode not in found]


def _order_compare_rows(plan: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fundcode_filter = plan.get("filter", {}).get("fundcode")
    if not isinstance(fundcode_filter, dict) or "$in" not in fundcode_filter:
        return rows
    requested = [str(item) for item in fundcode_filter["$in"]]
    by_code = {str(row.get("fundcode")): row for row in rows}
    ordered = [by_code[fundcode] for fundcode in requested if fundcode in by_code]
    extras = [row for row in rows if str(row.get("fundcode")) not in requested]
    return ordered + extras


def _latest_value(value: Any) -> tuple[Any, str]:
    if not isinstance(value, list) or not value:
        return value, ""
    dict_items = [item for item in value if isinstance(item, dict) and "value" in item]
    if not dict_items:
        return value, ""
    latest = max(dict_items, key=lambda item: str(item.get("btime", "")))
    return latest.get("value"), str(latest.get("btime", ""))
