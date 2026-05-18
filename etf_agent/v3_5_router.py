from __future__ import annotations

import json
from typing import Any

from .llm import parse_plan_json


ROUTES = {"realtime", "mongo_single", "mongo_report", "mongo_compare", "capability_clarify", "clarify", "unsupported"}

V3_5_ROUTER_SYSTEM_PROMPT = """你是 ETF 查询总路由器。

你只输出 JSON，不输出解释、Markdown 或最终答案。

你的任务只是在子链路之间选择，不生成 Mongo AST，不生成实时字段，不生成接口参数。

输出 schema:
{
  "route": "realtime|mongo_single|mongo_report|mongo_compare|capability_clarify|clarify|unsupported",
  "reason": "简短原因",
  "confidence": 0.0,
  "needs_fund_identity": false,
  "needs_clarification": false
}

路由含义:
- realtime: 实时价格、涨跌、成交、盘口、折溢价、内外盘、振幅、实时对比
- mongo_single: 基金基础资料、费率、基金经理、规模、跟踪指数等单基金资料
- mongo_report: 持仓、重仓、行业、概念、季报、年报等报告资料
- mongo_compare: 非实时的基金资料/收益/费率对比
- capability_clarify: 用户问题在实时行情和基金资料/收益/费率对比之间都合理，需要展示两边预览后追问
- clarify: 缺少标的或标的歧义，需要用户补充
- unsupported: 非 ETF、投资建议、当前系统能力外问题

重要判定:
- 如果用户只说“对比”并给出两个或多个 ETF 代码，但没有明确提出实时指标或资料字段，必须 route=capability_clarify。
- 如果用户对比涨跌幅、价格、成交、折溢价、盘口、内外盘，必须 route=realtime。
- 如果用户对比费率、规模、基金经理、持仓、收益、跟踪指数，必须 route=mongo_compare。
"""


def generate_v3_5_route_with_llm(*, question: str, config) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("阶段：v3.5 路由\n错误：缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    response = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": V3_5_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"question": question}, ensure_ascii=False, indent=2)},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    route = validate_v3_5_route(parse_plan_json(raw))
    return {
        "raw": raw,
        "route": route,
        "model": config.llm_model,
        "prompt_version": "v3.5-router-2026-05-17",
        "usage": _usage_dict(getattr(response, "usage", None)),
    }


def route_v3_5_locally(question: str, *, classification: dict[str, Any]) -> dict[str, Any]:
    mode = classification.get("recognized_query_mode")
    intent = classification.get("intent")
    reason = classification.get("reason") or classification.get("deny_reason")
    route = "unsupported"
    needs_fund_identity = False
    needs_clarification = False

    if reason == "field_not_imported" or "五档盘口" in question:
        route = "realtime"
    elif reason in {"v3_unsupported_domain", "unsupported_domain"} or any(word in question for word in ("贵州茅台", "上证指数", "深证成指")):
        route = "unsupported"
        reason = "unsupported_domain"
    elif mode == "clarify":
        route = "clarify"
        needs_clarification = True
    elif mode == "deny" and reason == "realtime_not_supported":
        route = "realtime"
    elif mode == "deny":
        route = "unsupported"
    elif mode == "report" or intent in {"report_industry", "report_holding", "report_concept"}:
        route = "mongo_report"
    elif mode == "compare":
        if _has_explicit_realtime_compare_metric(question):
            route = "realtime"
        else:
            route = "capability_clarify"
            needs_clarification = True
    elif mode in {"single", "filter", "search"}:
        route = "mongo_single"

    if "未识别标的" in str(reason):
        needs_fund_identity = True
        needs_clarification = True
        route = "clarify"

    return {
        "route": route,
        "reason": str(reason or intent or mode or "local classification"),
        "confidence": 1.0,
        "needs_fund_identity": needs_fund_identity,
        "needs_clarification": needs_clarification,
    }


def _has_explicit_realtime_compare_metric(question: str) -> bool:
    return any(
        term in question
        for term in (
            "价格",
            "涨跌",
            "涨跌幅",
            "成交",
            "溢价",
            "折价",
            "折溢价",
            "盘口",
            "买一",
            "卖一",
            "内外盘",
            "外盘",
            "内盘",
            "振幅",
        )
    )


def validate_v3_5_route(route: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(route, dict):
        raise ValueError("v3.5 route must be an object")
    route_name = route.get("route")
    if route_name not in ROUTES:
        raise ValueError(f"unknown v3.5 route: {route_name}")
    return {
        "route": route_name,
        "reason": str(route.get("reason") or ""),
        "confidence": float(route.get("confidence") or 0),
        "needs_fund_identity": bool(route.get("needs_fund_identity")),
        "needs_clarification": bool(route.get("needs_clarification")),
    }


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(key)
        result[key] = int(value or 0)
    return result
