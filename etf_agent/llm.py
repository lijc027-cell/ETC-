from __future__ import annotations

import json
import re
import warnings
from typing import Any

from .candidates import PERIOD_FIELDS


warnings.warn(
    "etf_agent.llm contains legacy v1 query-plan generation; v3 uses ast_generator.",
    DeprecationWarning,
    stacklevel=2,
)


SYSTEM_PROMPT = """你是 ETF 数据库查询计划生成器。

你的任务是根据用户问题、已抽取实体、候选字段，生成一个只读 Mongo 查询计划 JSON。

严格规则：
1. 只能使用输入中提供的候选字段和身份字段白名单。
2. 不允许编造集合名、字段名、过滤条件。
3. 只允许生成 find/find_one 等价的只读查询计划。
4. 不允许生成 insert、update、delete、drop、aggregate、$where、$regex、$ne、$gt、$lt、$in 等操作。
5. filter 只能使用 fundcode 或 thscode 的等值条件。
6. projection 必须是字段名字符串数组。
7. limit 必须是 1 到 20 的整数。
8. answer_fields 只能描述 projection 中的字段。
9. format 只能是 plain、yuan_to_100m、percent、date。
10. 只返回 JSON，不要返回 Markdown、解释文字或 sql_like。"""


def parse_plan_json(content: str) -> dict[str, Any]:
    cleaned = _strip_markdown(content.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Qwen 返回非法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Qwen 返回非法 JSON: 顶层不是 object")
    return data


def generate_query_plan(question: str, entities: dict, candidates: list[dict], config) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("阶段：查询计划生成\n错误：缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    user_prompt = _build_user_prompt(question, entities, candidates)
    response = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    return parse_plan_json(response.choices[0].message.content or "")


def is_plan_schema_like(plan: dict[str, Any]) -> bool:
    required = {"intent", "collection", "filter", "projection", "limit", "answer_fields"}
    if not required <= set(plan):
        return False
    if not isinstance(plan.get("answer_fields"), list):
        return False
    return all(isinstance(item, dict) for item in plan["answer_fields"])


def deterministic_plan(question: str, entities: dict, candidates: list[dict]) -> dict[str, Any]:
    if any(word in question for word in ("持仓", "重仓", "行业", "概念", "年报", "季报", "前十大", "搜索", "筛选", "对比", "实时行情")):
        return {
            "intent": "unsupported",
            "collection": "tb_ths_etf_base",
            "filter": {"fundcode": entities["fundcode"]},
            "projection": ["fundcode"],
            "limit": 1,
            "answer_fields": [{"field": "fundcode", "label": "基金代码", "unit": "", "format": "plain"}],
        }
    if any(word in question for word in ("盘子", "规模", "多大", "资产规模")):
        return _plan("fund_scale", entities["fundcode"], ["fundcode", "ths_fund_scale_fund"], candidates)
    if any(word in question for word in ("跟踪", "跟的", "指数", "标的指数")):
        return _plan("tracking_index", entities["fundcode"], ["fundcode", "ths_tracking_index_code_fund", "ths_name_of_tracking_index_fund"], candidates)
    if any(word in question for word in ("管理费", "托管费", "费率", "贵不贵")):
        projection = ["fundcode", "ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"]
        if any(word in question for word in ("基金经理", "谁在管", "管理人")):
            projection.extend(["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"])
            return _plan("fee_and_manager", entities["fundcode"], projection, candidates)
        return _plan("fee", entities["fundcode"], projection, candidates)
    if any(word in question for word in ("基金经理", "谁在管", "管理人")):
        return _plan("manager", entities["fundcode"], ["fundcode", "ths_fund_manager_current_fund", "ths_fund_supervisor_fund"], candidates)
    if "分红" in question:
        return _plan("dividend", entities["fundcode"], ["fundcode", "ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"], candidates)
    if any(word in question for word in ("表现", "收益率", "收益", "涨跌", "赚了", "回报", "各周期")):
        return _plan("performance", entities["fundcode"], ["fundcode", *PERIOD_FIELDS.get(entities.get("period", "1y"), PERIOD_FIELDS["1y"])], candidates)
    return _plan(
        "basic_info",
        entities["fundcode"],
        ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_name_of_tracking_index_fund", "ths_fund_scale_fund"],
        candidates,
    )


def _plan(intent: str, fundcode: str, projection: list[str], candidates: list[dict]) -> dict[str, Any]:
    labels = {candidate["field"]: candidate["cn_name"] for candidate in candidates}
    descriptions = {candidate["field"]: candidate.get("description", "") for candidate in candidates}
    answer_fields = []
    for field in projection:
        answer_fields.append(
            {
                "field": field,
                "label": labels.get(field, "基金代码" if field == "fundcode" else field),
                "unit": _guess_unit(field, descriptions.get(field, "")),
                "format": _guess_format(field, descriptions.get(field, "")),
            }
        )
    return {
        "intent": intent,
        "collection": "tb_ths_etf_base",
        "filter": {"fundcode": fundcode},
        "projection": projection,
        "limit": 1,
        "answer_fields": answer_fields,
    }


def _guess_format(field: str, description: str) -> str:
    if "单位：元" in description:
        return "yuan_to_100m"
    if "rank" in field:
        return "plain"
    if "fee_rate" in field or "yeild" in field:
        return "percent"
    return "plain"


def _guess_unit(field: str, description: str) -> str:
    if "单位：元" in description:
        return "元"
    if "fee_rate" in field or ("yeild" in field and "rank" not in field):
        return "%"
    return ""


def _build_user_prompt(question: str, entities: dict, candidates: list[dict]) -> str:
    return f"""用户问题：
{question}

实体抽取结果：
{json.dumps(entities, ensure_ascii=False)}

允许的身份字段：
["fundcode", "thscode", "ths_fund_extended_inner_short_name_fund"]

候选字段：
{json.dumps(candidates, ensure_ascii=False, indent=2)}

只允许输出以下 6 个顶层字段：intent、collection、filter、projection、limit、answer_fields。
answer_fields 必须是 object 数组，不能是字符串数组。

示例输出：
{{
  "intent": "fund_scale",
  "collection": "tb_ths_etf_base",
  "filter": {{"fundcode": "510300"}},
  "projection": ["fundcode", "ths_fund_scale_fund"],
  "limit": 1,
  "answer_fields": [
    {{"field": "ths_fund_scale_fund", "label": "基金规模", "unit": "元", "format": "yuan_to_100m"}}
  ]
}}

请只输出符合 schema 的查询计划 JSON。"""


def _strip_markdown(content: str) -> str:
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.S)
    return match.group(1) if match else content
