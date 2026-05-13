from __future__ import annotations

from typing import Any


def build_boundary_answer(
    question: str,
    classification: dict[str, Any],
    *,
    snapshot_result: dict[str, Any] | None = None,
    partial_context: dict[str, Any] | None = None,
) -> str:
    routing_type = _routing_type(classification)
    reason = _reason(classification)

    if routing_type == "DeniedQuery":
        if reason == "realtime_not_supported":
            fallback = _realtime_snapshot_fallback(question, snapshot_result)
            if fallback:
                return fallback
            return "这套远端库不提供实时行情。"
        if reason == "investment_advice":
            if any(word in question for word in ("能买吗", "能不能买", "值不值得", "该不该买")):
                return "这属于投资建议问题，我不直接回答“能不能买”。"
            return "这个属于投资建议，我不直接给推荐。"
        if reason == "unsupported_domain":
            return "这个超出当前 ETF 数据库查询范围，我这里没有大盘实时或当日综述数据。"
        return "抱歉，该问题超出当前 ETF 数据查询能力范围。"

    if routing_type == "ClarificationRequired":
        if reason == "invalid_fundcode":
            return "这不是有效的 ETF 代码，当前也查不到对应基金。"
        return "查询条件还不够明确，请补充后重试。"

    if partial_context and partial_context.get("type") == "partial_compare":
        return _partial_compare_answer(partial_context)

    if partial_context and partial_context.get("type") == "premise_correction":
        return _premise_correction_answer(partial_context)

    if reason == "data_not_available":
        return "暂无数据。"
    return "当前版本暂不支持该查询类型。"


def _routing_type(classification: dict[str, Any]) -> str:
    mode = classification.get("recognized_query_mode")
    if mode == "deny":
        return "DeniedQuery"
    if mode == "clarify":
        return "ClarificationRequired"
    return "UnsupportedQuery"


def _reason(classification: dict[str, Any]) -> str | None:
    reason = classification.get("deny_reason") or classification.get("reason")
    if reason == "v3_unsupported_domain":
        return "unsupported_domain"
    return reason


def _realtime_snapshot_fallback(question: str, snapshot_result: dict[str, Any] | None) -> str | None:
    data = (snapshot_result or {}).get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return None
    fundcode = str(data.get("fundcode") or _extract_fundcode(question) or "该 ETF")
    nv = _latest_point(data.get("ths_unit_nv_fund"))
    if not nv or nv.get("value") in (None, ""):
        return None
    return f"这套远端库不提供实时行情。当前能直接查到的是最新净值，{fundcode} 在 {nv['btime']} 的单位净值是 {float(nv['value']):.4f}。"


def _partial_compare_answer(partial_context: dict[str, Any]) -> str:
    found = partial_context.get("found") or []
    missing = partial_context.get("missing") or []
    table = partial_context.get("table") or ""
    found_text = "、".join(found) if found else "可查代码"
    missing_text = "、".join(missing) if missing else "未查到代码"
    prefix = f"{found_text} 能查到，{missing_text} 未查到。下面是 {found_text} 的可查数据："
    return f"{prefix}\n\n{table}".strip()


def _premise_correction_answer(partial_context: dict[str, Any]) -> str:
    fundcode = partial_context.get("fundcode") or "该 ETF"
    period = partial_context.get("report_period") or "最新季报"
    industries = partial_context.get("industries") or []
    if industries:
        return f"就 {fundcode} 来说，并不属于“季报年报都没有”的情况。当前远端库里有 {period}持仓行业数据：{'、'.join(industries)}。"
    return f"就 {fundcode} 来说，并不属于“季报年报都没有”的情况。"


def _extract_fundcode(question: str) -> str:
    import re

    match = re.search(r"(?<!\d)\d{6}(?!\d)", question)
    return match.group(0) if match else ""


def _latest_point(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        points = [item for item in value if isinstance(item, dict) and item.get("value") not in (None, "")]
        if not points:
            return None
        return max(points, key=lambda item: str(item.get("btime", "")))
    if isinstance(value, dict) and value.get("value") not in (None, ""):
        return value
    return None
