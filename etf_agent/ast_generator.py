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
   intent, sub_intents, from, select, where, order_by, limit, output_style, answer_fields, report_period, expand
3. intent 只能使用 capability.intent。
4. from 只能使用 capability.from。
5. select 必须是字符串数组，不要输出对象、alias、label 或任何嵌套结构。
6. answer_fields[].field 必须是 select 中的真实字段名，不要写 alias。
7. select 和 answer_fields[].field 只能来自 selectable_fields。
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
        raise RuntimeError("阶段：v3.2 AST Draft 生成\n错误：缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

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
    return {
        "raw": raw,
        "draft": draft,
        "model": config.llm_model,
        "prompt_version": "v3.2-full-ast-2026-05-08",
    }
