from __future__ import annotations

from copy import deepcopy
import warnings
from typing import Any

from .candidates import PERIOD_FIELDS
from .dictionary import FieldMapping, collection_fields


warnings.warn(
    "etf_agent.plan validates legacy v1 query plans; v3 uses AST validation and compiled_query.",
    DeprecationWarning,
    stacklevel=2,
)


IDENTITY_FIELDS = {"fundcode", "thscode", "ths_fund_extended_inner_short_name_fund"}
ALLOWED_TOP_KEYS = {"intent", "collection", "filter", "projection", "limit", "answer_fields"}
ALLOWED_FORMATS = {"plain", "yuan_to_100m", "percent", "date"}
FORBIDDEN_WORDS = ("insert", "update", "delete", "drop")

INTENT_FIELDS = {
    "basic_info": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_name_of_tracking_index_fund",
        "ths_fund_scale_fund",
    ],
    "fund_scale": ["ths_fund_scale_fund"],
    "tracking_index": ["ths_tracking_index_code_fund", "ths_name_of_tracking_index_fund"],
    "fee": ["ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"],
    "manager": ["ths_fund_manager_current_fund", "ths_fund_supervisor_fund"],
    "dividend": ["ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"],
    "fee_and_manager": [
        "ths_manage_fee_rate_fund",
        "ths_mandate_fee_rate_fund",
        "ths_fund_manager_current_fund",
        "ths_fund_supervisor_fund",
    ],
}
V1_INTENTS = set(INTENT_FIELDS) | {"performance"}
V1_COLLECTION = "tb_ths_etf_base"
INTENT_ALIASES = {
    "fund_basic_info": "basic_info",
    "fund_performance": "performance",
    "fund_manager": "manager",
    "fund_fee": "fee",
    "fund_fee_and_manager": "fee_and_manager",
    "dividend_record": "dividend",
    "fund_dividend": "dividend",
    "track_index": "tracking_index",
    "tracking": "tracking_index",
    "scale": "fund_scale",
}


class PlanValidationError(ValueError):
    pass


def validate_query_plan(
    raw_plan: dict[str, Any],
    mappings: list[FieldMapping],
    entities: dict[str, str],
    candidate_ids: list[str],
) -> dict[str, Any]:
    plan = deepcopy(raw_plan)
    _validate_shape(plan)
    _normalize_intent(plan)
    _validate_v1_scope(plan)
    _validate_forbidden_words(plan)
    _validate_filter(plan)
    completed_fields = _complete_projection(plan, mappings, entities)
    _complete_answer_fields(plan, mappings)
    _validate_fields(plan, mappings, candidate_ids, completed_fields)
    return plan


def build_sql_like(plan: dict[str, Any]) -> str:
    key, value = next(iter(plan["filter"].items()))
    escaped = str(value).replace("'", "''")
    return (
        f"SELECT {', '.join(plan['projection'])}\n"
        f"FROM {plan['collection']}\n"
        f"WHERE {key} = '{escaped}'\n"
        f"LIMIT {plan['limit']};"
    )


def mongo_params(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "collection": plan["collection"],
        "filter": plan["filter"],
        "projection": {field: 1 for field in plan["projection"]} | {"_id": 0},
        "limit": plan["limit"],
    }


def _validate_shape(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict):
        raise PlanValidationError("查询计划必须是 JSON object")
    extra = set(plan) - ALLOWED_TOP_KEYS
    if extra:
        raise PlanValidationError(f"查询计划包含未知顶层字段: {sorted(extra)}")
    missing = ALLOWED_TOP_KEYS - set(plan)
    if missing:
        raise PlanValidationError(f"查询计划缺少必填字段: {sorted(missing)}")
    if not isinstance(plan["collection"], str) or not isinstance(plan["intent"], str):
        raise PlanValidationError("collection 和 intent 必须是字符串")
    if not isinstance(plan["projection"], list) or not all(isinstance(v, str) for v in plan["projection"]):
        raise PlanValidationError("projection 必须是字段名字符串数组")
    if not isinstance(plan["limit"], int) or not 1 <= plan["limit"] <= 20:
        raise PlanValidationError("limit 必须是 1 到 20 之间的整数")
    if not isinstance(plan["answer_fields"], list):
        raise PlanValidationError("answer_fields 必须是数组")


def _normalize_intent(plan: dict[str, Any]) -> None:
    plan["intent"] = INTENT_ALIASES.get(plan["intent"], plan["intent"])
    if plan["intent"] in V1_INTENTS:
        return
    lower = plan["intent"].lower()
    if any(keyword in lower for keyword in ("yield", "return", "performance")):
        plan["intent"] = "performance"
    elif "manager" in lower:
        plan["intent"] = "manager"
    elif "dividend" in lower or "分红" in lower:
        plan["intent"] = "dividend"


def _validate_v1_scope(plan: dict[str, Any]) -> None:
    if plan["collection"] != V1_COLLECTION:
        raise PlanValidationError(f"v1 暂不支持 collection {plan['collection']}")
    if plan["intent"] not in V1_INTENTS:
        raise PlanValidationError(f"v1 暂不支持 intent {plan['intent']}")


def _validate_forbidden_words(plan: dict[str, Any]) -> None:
    text = repr(plan).lower()
    for word in FORBIDDEN_WORDS:
        if word in text:
            raise PlanValidationError(f"查询计划包含禁止写操作语义: {word}")


def _validate_filter(plan: dict[str, Any]) -> None:
    filters = plan["filter"]
    if not isinstance(filters, dict) or len(filters) != 1:
        raise PlanValidationError("filter 第一版只允许单个等值过滤字段")
    key, value = next(iter(filters.items()))
    if key.startswith("$"):
        raise PlanValidationError("filter key 不能以 $ 开头")
    if key not in {"fundcode", "thscode"}:
        raise PlanValidationError("filter 第一版只允许 fundcode 或 thscode")
    if isinstance(value, (dict, list)):
        raise PlanValidationError("filter value 不允许 object 或 array")
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        raise PlanValidationError("filter value 只允许 string、number、boolean、null 标量")


def _complete_projection(plan: dict[str, Any], mappings: list[FieldMapping], entities: dict[str, str]) -> set[str]:
    fields = list(dict.fromkeys(plan["projection"]))
    if plan["intent"] == "performance":
        required = PERIOD_FIELDS.get(entities.get("period", "1y"), PERIOD_FIELDS["1y"])
    else:
        required = INTENT_FIELDS.get(plan["intent"], [])
    completed = set()
    for field in required:
        if field not in fields:
            fields.append(field)
            completed.add(field)
    plan["projection"] = fields
    return completed


def _complete_answer_fields(plan: dict[str, Any], mappings: list[FieldMapping]) -> None:
    by_field = {item.field: item for item in mappings if item.collection == plan["collection"]}
    existing = {item.get("field") for item in plan["answer_fields"] if isinstance(item, dict)}
    for field in plan["projection"]:
        if field in existing:
            continue
        mapping = by_field.get(field)
        if mapping:
            plan["answer_fields"].append(
                {"field": field, "label": mapping.cn_name, "unit": _unit(mapping), "format": _format(mapping)}
            )


def _validate_fields(
    plan: dict[str, Any],
    mappings: list[FieldMapping],
    candidate_ids: list[str],
    completed_fields: set[str],
) -> None:
    collections = collection_fields(mappings)
    if plan["collection"] not in collections:
        raise PlanValidationError(f"未知 collection: {plan['collection']}")

    allowed_candidates = set(candidate_ids)
    template_fields = _template_fields(plan)
    if not candidate_ids:
        unexpected = [
            field
            for field in plan["projection"]
            if field not in IDENTITY_FIELDS and field not in completed_fields and field not in template_fields
        ]
        if unexpected:
            raise PlanValidationError(f"候选字段为空，projection 包含非模板字段 {unexpected[0]}")
    fields = collections[plan["collection"]]
    for field in plan["projection"]:
        if field not in fields:
            raise PlanValidationError(f"projection 包含未知字段 {field}")
        if fields[field].type in {"array", "object"}:
            raise PlanValidationError(f"第一版禁止 projection array/object 字段 {field}")
        if (
            field not in IDENTITY_FIELDS
            and field not in completed_fields
            and field not in template_fields
            and candidate_ids
            and f"{plan['collection']}.{field}" not in allowed_candidates
        ):
            raise PlanValidationError(f"projection 字段不在候选字段范围内 {field}")

    projection = set(plan["projection"])
    for item in plan["answer_fields"]:
        if not isinstance(item, dict):
            raise PlanValidationError("answer_fields 每项必须是 object")
        unknown = set(item) - {"field", "label", "unit", "format"}
        if unknown:
            raise PlanValidationError(f"answer_fields 包含未知字段: {sorted(unknown)}")
        if item.get("field") not in projection:
            raise PlanValidationError("answer_fields[].field 必须存在于 projection")
        if item.get("format", "plain") not in ALLOWED_FORMATS:
            raise PlanValidationError("answer_fields[].format 不合法")


def _unit(mapping: FieldMapping) -> str:
    if "单位：元" in mapping.description:
        return "元"
    if "百分比" in mapping.description or "收益率" in mapping.cn_name or "费率" in mapping.cn_name:
        return "%"
    return ""


def _template_fields(plan: dict[str, Any]) -> set[str]:
    if plan["intent"] == "performance":
        return {
            field
            for fields in PERIOD_FIELDS.values()
            for field in fields
        }
    return set(INTENT_FIELDS.get(plan["intent"], []))


def _format(mapping: FieldMapping) -> str:
    if "单位：元" in mapping.description:
        return "yuan_to_100m"
    if "百分比" in mapping.description or "收益率" in mapping.cn_name or "费率" in mapping.cn_name:
        return "percent"
    if "日期" in mapping.cn_name or "日" in mapping.cn_name:
        return "date"
    return "plain"
