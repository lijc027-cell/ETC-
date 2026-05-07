from __future__ import annotations

from typing import Any


def format_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
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
    if fmt == "yuan_to_100m":
        return f"{float(value) / 100000000:.2f} 亿元{suffix}"
    if fmt == "percent":
        return f"{float(value):.2f}%{suffix}"
    if isinstance(value, float):
        return f"{value:.4g}{suffix}"
    return f"{value}{suffix}"


def _latest_value(value: Any) -> tuple[Any, str]:
    if not isinstance(value, list) or not value:
        return value, ""
    dict_items = [item for item in value if isinstance(item, dict) and "value" in item]
    if not dict_items:
        return value, ""
    latest = max(dict_items, key=lambda item: str(item.get("btime", "")))
    return latest.get("value"), str(latest.get("btime", ""))
