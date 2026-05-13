from __future__ import annotations

from typing import Any


def select_candidate_fundcodes(rows: list[dict[str, Any]], *, keyword: str = "", limit: int = 1) -> list[str]:
    candidates = [row for row in rows if isinstance(row, dict) and row.get("fundcode")]
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda row: _score(row, keyword), reverse=True)
    return [str(row["fundcode"]) for row in ranked[:limit]]


def clarification_for_candidates(rows: list[dict[str, Any]], *, keyword: str = "", limit: int = 5) -> dict[str, Any] | None:
    candidates = [row for row in rows if isinstance(row, dict) and row.get("fundcode")]
    if len(candidates) <= 1:
        return None
    ranked = sorted(candidates, key=lambda row: _score(row, keyword), reverse=True)
    options = [_candidate_option(row, keyword) for row in ranked[:limit]]
    if len(options) <= 1:
        return None
    return {
        "type": "ClarificationRequired",
        "reason": "multiple_candidates",
        "options": options,
    }


def _score(row: dict[str, Any], keyword: str) -> tuple[int, float, str]:
    index_name = str(row.get("ths_name_of_tracking_index_fund") or "")
    short_name = str(row.get("ths_fund_extended_inner_short_name_fund") or "")
    keyword = keyword.strip()
    semantic = 0
    if keyword and index_name == f"{keyword}指数":
        semantic = 100
    elif keyword and index_name == keyword:
        semantic = 95
    elif keyword and keyword in index_name:
        semantic = 80
    elif keyword and keyword in short_name:
        semantic = 70
    if any(word in index_name or word in short_name for word in ("低波", "低波动", "质量", "红利低波")):
        semantic -= 25
    return semantic, _latest_number(row.get("ths_fund_scale_fund")), str(row.get("fundcode"))


def _candidate_option(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    index_name = str(row.get("ths_name_of_tracking_index_fund") or "")
    short_name = str(row.get("ths_fund_extended_inner_short_name_fund") or "")
    scale = row.get("ths_fund_scale_fund")
    exact = bool(keyword and index_name == f"{keyword}指数")
    return {
        "fundcode": str(row.get("fundcode") or ""),
        "label": short_name,
        "tracking_index": index_name,
        "scale": _format_amount(scale),
        "match_reason": "跟踪指数精确匹配，规模较大" if exact and _latest_number(scale) else "跟踪指数精确匹配" if exact else "名称或指数相关",
    }


def _latest_number(value: Any) -> float:
    if isinstance(value, list):
        points = [item for item in value if isinstance(item, dict) and item.get("value") is not None]
        if not points:
            return 0.0
        latest = max(points, key=lambda item: str(item.get("btime", "")))
        value = latest.get("value")
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_amount(value: Any) -> str:
    number = _latest_number(value)
    if not number:
        return "暂无数据"
    return f"{number / 100000000:.2f} 亿元"
