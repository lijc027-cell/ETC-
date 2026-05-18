from __future__ import annotations

import json
from typing import Any

from .llm import parse_plan_json


REALTIME_PLAN_SYSTEM_PROMPT = """你是 ETF 实时行情 query plan 生成器。

你只输出 JSON，不输出解释、Markdown 或最终答案。

严格规则：
1. 顶层必须是 {"type":"executable_query","subqueries":[...]}。
2. subqueries 每项必须包含 id、intent_profile、metrics、time_scope、presentation。
3. intent_profile 只能是 quote、overview、trading、valuation、order_book、trade_flow、technical。
4. metrics 只输出 field、source、required；field 只能来自候选 fields。
5. time_scope 第一版只能是 {"kind":"realtime"}。
6. 不输出 endpoint、HTTP body、Mongo collection/filter/projection。
7. 多意图用一个 subquery 的多个 metrics 或多个 subqueries 表达，优先保持简单。
8. 如果用户问题语义模糊但确认为想看实时情况，使用 overview。
"""


def generate_realtime_plan_with_llm(
    *,
    question: str,
    fund_resolution: dict[str, Any],
    registry: dict[str, Any],
    config,
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("阶段：v3.5 realtime plan 生成\n错误：缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    payload = {
        "question": question,
        "fund_resolution": fund_resolution,
        "intent_profiles": _intent_profile_cards(registry),
        "fields": _field_cards(registry),
        "output_contract": {
            "type": "executable_query",
            "subquery_required_keys": ["id", "intent_profile", "metrics", "time_scope", "presentation"],
        },
    }
    response = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": REALTIME_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    draft = parse_plan_json(raw)
    return {
        "raw": raw,
        "draft": draft,
        "model": config.llm_model,
        "prompt_version": "v3.5-realtime-plan-2026-05-17",
        "usage": _usage_dict(getattr(response, "usage", None)),
    }


def _intent_profile_cards(registry: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for scenario, row in registry["intent_to_scenario_matrix"].items():
        if scenario in {"overview", "default_overview"}:
            continue
        cards.append(
            {
                "intent_profile": _scenario_to_intent_profile(scenario),
                "scenario": scenario,
                "description": "、".join(row.get("any_of") or []),
                "default_fields": registry["scenario_to_fields_matrix"].get(scenario) or [],
            }
        )
    default_overview = registry.get("default_overview") or {}
    default_overview_scenario = str(default_overview.get("scenario") or "default_overview")
    cards.append(
        {
            "intent_profile": "overview",
            "scenario": default_overview_scenario,
            "description": "语义模糊但可判定为想看实时情况",
            "default_fields": default_overview.get("fields")
            or registry["scenario_to_fields_matrix"].get(default_overview_scenario)
            or [],
        }
    )
    cards.append(
        {
            "intent_profile": "technical",
            "scenario": "overview",
            "description": "振幅、波动、震荡",
            "default_fields": ["swing"],
        }
    )
    return cards


def _field_cards(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "label": registry["field_display_matrix"][field]["label"],
            "value_type": meta.get("value_type"),
        }
        for field, meta in registry["field_metadata"].items()
    ]


def _scenario_to_intent_profile(scenario: str) -> str:
    return {
        "price_change": "quote",
        "overview": "overview",
        "trading": "trading",
        "valuation": "valuation",
        "order_book": "order_book",
        "trade_flow": "trade_flow",
    }.get(scenario, scenario)


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
