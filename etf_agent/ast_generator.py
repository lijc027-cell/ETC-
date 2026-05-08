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
