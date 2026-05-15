from __future__ import annotations

import json
from typing import Any

from .llm import parse_plan_json


SYSTEM_PROMPT = """你是 ETF 查询 AST 字段选择器。

你只能根据 selection_context 选择 select 和 answer_fields。
严格规则：
1. 只返回 JSON object。
2. 只允许顶层字段 select 和 answer_fields。
3. 不允许输出 where、filter、order_by、limit、intent、collection。
4. select 只能来自 selection_context.selectable_fields。
5. answer_fields[].field 必须来自 select。
6. answer_fields[].format 只能来自 selection_context.allowed_formats。
"""

FULL_AST_SYSTEM_PROMPT = """你是 ETF Text-to-Query AST 生成器。

你只生成受限 JSON AST，不生成 SQL、PyMongo、解释文字或最终答案。

严格规则：
1. 只返回一个 JSON object。
2. 必须包含顶层字段：
   intent, sub_intents, from, select, where, order_by, limit, output_style, answer_fields, timeseries_semantics, report_period, expand
   当 generation_context.phase 为 v3.3 时，还必须包含 ast_schema_version；v3.2 base AST 不要输出 ast_schema_version。
3. intent 只能使用 capability.intent。
4. from 只能使用 capability.from。
5. select 默认是字段名字符串数组；只有当 generation_context.grammar_fragment_id == "derived_performance" 时，收益率 select 必须使用 {"alias":"return_<period>","type":"derived_return","period":"<period>"} 对象，identity/rank/context 字段仍使用字符串。
6. answer_fields[].field 必须来自 select 中的字段名或 derived_return alias；非 derived 字段不要写 alias。
7. 普通物理字段只能来自 selectable_fields；derived_return alias 必须来自 required_derived_aliases，answer_fields 中的 derived alias 必须写 source="derived"。
8. where[].field 只能来自 where_constraints.field_operators 的 key。
9. where[].op 只能来自该 field 对应的 operator 列表。
10. order_by 为 null，或 field 来自 sortable_fields，direction 只能是 asc/desc。
11. limit 必须遵守 limit_policy。
12. 不要从 evidence 之外编造用户没问的语义字段、筛选条件、排序或 limit。
13. answer_fields 只能描述 select 中的字段，format 只能来自 answer_field_formats。
14. report_period 和 expand 在当前 v3.2 base 范围内通常为 null。
15. 如果 generation_context.child_task 明确说明这是 two_step_composite 的 step 2 compare，那么不要再生成 order_by，不要重新挑选候选集，只对上一步传入的 fundcodes 做 compare。
16. generation_context.strict_validation_contract 是本次用户问题的硬校验合同：
    - required_select_fields 必须全部出现在 select。
    - required_answer_fields 必须全部出现在 answer_fields[].field。
    - expected_where 必须逐条出现在 where。
    - expected_order_by 非 null 时必须原样出现在 order_by。
    - expected_limit 非 null 时必须作为 limit。
    - expected_sub_intents 非空时必须原样作为 sub_intents；为空时 sub_intents 必须为 []。
17. 如果 generation_context.strict_validation_contract.expected_timeseries_modes 非空，必须在 timeseries_semantics.by_field 中逐字段输出对应 mode；`latest_two` 不能被压成 `latest`。
    如果 expected_timeseries_modes 为空，timeseries_semantics 必须为 null；不要输出空 by_field，也不要把 return_* 派生收益率写入 timeseries_semantics。
18. v3.3 AST 的 ast_schema_version 必须原样等于 generation_context.ast_schema_version，只能是 v3_2_base_ast 或 v3_3_structured_query。
19. 如果 generation_context.derived_performance_contract 非空，必须输出 grammar_fragment_id="derived_performance"、compiler_rule_id、profile，并按 required_derived_aliases 输出 derived_return select 对象；required_performance_rows 非空时必须输出匹配的 performance_rows；不得用 ths_yeild_*_fund 代替派生收益率语义。
    derived_performance_contract 非空时，收益率只通过 derived_return select 表达；timeseries_semantics 必须为 null。
"""


def generate_ast_fields_with_llm(
    question: str,
    *,
    classification: dict[str, Any],
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
    config,
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("阶段：v3 AST 字段生成\n错误：缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    response = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "recognized_query_mode": classification.get("recognized_query_mode"),
                        "intent": classification.get("intent"),
                        "entity_hints": entity_hints,
                        "selection_context": selection_context,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
        temperature=0,
    )
    data = parse_plan_json(response.choices[0].message.content or "")
    extra = set(data) - {"select", "answer_fields"}
    if extra:
        raise ValueError(f"LLM AST contains forbidden keys: {sorted(extra)}")
    if not isinstance(data.get("select"), list) or not isinstance(data.get("answer_fields"), list):
        raise ValueError("LLM AST must contain select and answer_fields arrays")
    return data


def generate_full_ast_draft_with_llm(
    *,
    question: str,
    routing_result: dict[str, Any],
    classification: dict[str, Any],
    generation_context: dict[str, Any],
    config,
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("阶段：v3 AST 字段生成\n错误：缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    payload = {
        "question": question,
        "routing_result": routing_result,
        "recognized_query_mode": classification.get("recognized_query_mode"),
        "intent_candidates": classification.get("intent_candidates", []),
        "blocked_intent_candidates": classification.get("blocked_intent_candidates", []),
        "generation_context": generation_context["llm_context"],
    }
    response = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": FULL_AST_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    draft = parse_plan_json(raw)
    extra = set(draft) - {
        "ast_schema_version",
        "intent",
        "sub_intents",
        "from",
        "select",
        "where",
        "order_by",
        "limit",
        "output_style",
        "answer_fields",
        "timeseries_semantics",
        "report_period",
        "expand",
        "grammar_fragment_id",
        "compiler_rule_id",
        "profile",
        "performance_rows",
    }
    if extra:
        raise ValueError(f"LLM AST contains forbidden keys: {sorted(extra)}")
    if not isinstance(draft.get("select"), list) or not isinstance(draft.get("answer_fields"), list):
        raise ValueError("LLM AST must contain select and answer_fields arrays")
    return {
        "raw": raw,
        "draft": draft,
        "model": config.llm_model,
        "prompt_version": "v3.2-full-ast-2026-05-08",
        "usage": _usage_dict(getattr(response, "usage", None)),
    }


def _local_full_ast_payload(
    *,
    question: str,
    routing_result: dict[str, Any],
    classification: dict[str, Any],
    generation_context: dict[str, Any],
) -> dict[str, Any]:
    draft = _build_local_full_ast_draft(
        question=question,
        routing_result=routing_result,
        classification=classification,
        generation_context=generation_context,
    )
    return {
        "raw": json.dumps(draft, ensure_ascii=False, indent=2),
        "draft": draft,
        "model": "local-fallback",
        "prompt_version": "v3.2-full-ast-2026-05-08",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _build_local_full_ast_draft(
    *,
    question: str,
    routing_result: dict[str, Any],
    classification: dict[str, Any],
    generation_context: dict[str, Any],
) -> dict[str, Any]:
    llm_context = generation_context["llm_context"]
    expectations = generation_context["validator_expectations"]
    selection_context = generation_context["selection_context"]
    capability = llm_context["capability"]
    phase = llm_context.get("phase", "v3.2")
    base_draft = {
        "intent": classification.get("intent") or capability["intent"],
        "sub_intents": list(expectations.get("expected_sub_intents") or []),
        "from": capability["from"],
        "select": _local_select_fields(question, llm_context, expectations),
        "where": [dict(clause) for clause in expectations.get("expected_where") or []],
        "order_by": _local_order_by(expectations),
        "limit": _local_limit(llm_context, expectations),
        "output_style": capability["output_style"],
        "answer_fields": _local_answer_fields(selection_context, expectations),
        "timeseries_semantics": None,
        "report_period": None,
        "expand": None,
    }
    if phase in {"v3.3", "v3.4"}:
        base_draft["ast_schema_version"] = llm_context.get("ast_schema_version", "v3_3_structured_query")
    if llm_context.get("derived_performance_contract"):
        return _local_derived_full_ast_draft(base_draft, llm_context, expectations, selection_context)
    if expectations.get("expected_timeseries_modes"):
        base_draft["timeseries_semantics"] = {
            "by_field": {
                field: dict(spec)
                for field, spec in expectations["expected_timeseries_modes"].items()
            }
        }
    return base_draft


def _local_select_fields(question: str, llm_context: dict[str, Any], expectations: dict[str, Any]) -> list[str]:
    fields = list(expectations.get("required_select_fields") or [])
    if llm_context.get("derived_performance_contract"):
        fields = list(fields)
    return list(dict.fromkeys(fields))


def _local_answer_fields(selection_context: dict[str, Any], expectations: dict[str, Any]) -> list[dict[str, Any]]:
    fields = list(expectations.get("required_answer_fields") or expectations.get("required_select_fields") or [])
    return [{"field": field} for field in fields]


def _local_order_by(expectations: dict[str, Any]) -> dict[str, Any] | None:
    order_by = expectations.get("expected_order_by")
    return dict(order_by) if isinstance(order_by, dict) else None


def _local_limit(llm_context: dict[str, Any], expectations: dict[str, Any]) -> int:
    if expectations.get("expected_limit") is not None:
        return int(expectations["expected_limit"])
    policy = llm_context.get("limit_policy") or {"default": 1}
    return int(policy.get("default", 1))


def _local_derived_full_ast_draft(
    base_draft: dict[str, Any],
    llm_context: dict[str, Any],
    expectations: dict[str, Any],
    selection_context: dict[str, Any],
) -> dict[str, Any]:
    derived = dict(base_draft)
    contract = llm_context["derived_performance_contract"]
    aliases = list(contract.get("required_derived_aliases") or [])
    period_defaults = contract.get("period_defaults") or {}
    default_period = period_defaults.get("default", "1y")
    select_items: list[dict[str, Any]] = []
    for alias in aliases:
        period = alias.removeprefix("return_") if alias.startswith("return_") else default_period
        select_items.append({"alias": alias, "type": "derived_return", "period": period})
    derived["grammar_fragment_id"] = "derived_performance"
    derived["compiler_rule_id"] = contract.get("compiler_rule_id")
    derived["profile"] = contract.get("allowed_profiles", ["derived_performance_table"])[0]
    derived["select"] = _merge_derived_select_items(derived["select"], select_items, aliases)
    answer_fields = list(derived["answer_fields"])
    for alias in aliases:
        if alias not in {item.get("field") for item in answer_fields if isinstance(item, dict)}:
            answer_fields.append({"field": alias, "source": "derived", "format": "percent"})
    derived["answer_fields"] = answer_fields
    if contract.get("required_performance_rows"):
        derived["performance_rows"] = [
            {
                "alias": alias,
                "period": alias.removeprefix("return_") if alias.startswith("return_") else default_period,
                "label": contract.get("performance_row_labels", {}).get(alias, alias),
            }
            for alias in contract["required_performance_rows"]
        ]
    else:
        derived["performance_rows"] = []
    derived["timeseries_semantics"] = None
    return derived


def _merge_derived_select_items(
    existing: list[Any],
    derived_items: list[dict[str, Any]],
    aliases: list[str],
) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    alias_set = set(aliases)
    for item in existing:
        if isinstance(item, str) and item in alias_set:
            continue
        key = item if isinstance(item, str) else json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        merged.append(item)
        seen.add(key)
    for item in derived_items:
        alias = str(item.get("alias") or "")
        if alias in seen:
            continue
        merged.append(item)
        seen.add(alias)
    return merged


def _usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    data = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if value is None:
            continue
        data[key] = int(value)
    return data or None
